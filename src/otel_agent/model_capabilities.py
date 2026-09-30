"""Model capability metadata backfill for the /v1/models endpoint.

Every model entry may carry four additive fields — ``context_length``,
``max_output_tokens``, ``input_modalities``, ``output_modalities`` — sourced
in a fixed chain (R5): upstream passthrough → OpenRouter public catalog
backfill → whole-field omission. This module owns the backfill source: the
whole OpenRouter catalog (``https://openrouter.ai/api/v1/models``) fetched
once and cached in-process.

KTD1 — ``lookup()`` is synchronous and pure-local: it NEVER touches the
network. The network only happens in a background refresh thread: a cold-start
prefetch at process start (``warm_up()``), a stale-while-revalidate trigger
when the 24h TTL expires, and a trigger when no cache exists at all. Refreshes
are single-flight (at most one fetch in the air) with a 5-minute failure
cooldown. On failure the previous table keeps serving (stale-on-error) until
``fetched_at`` is more than 7 days old; beyond that the table counts as
absent. Nothing is written to disk — the catalog is a few hundred KB and is
cheap to rebuild in-process.

KTD2 — matching is normalized exact match: lowercase, vendor aliases
(``xai``↔``x-ai``), version-separator fold (``v-2.5``↔``v2.5``). Variant
suffixes (``:batch``, ``:free``) stay part of the id and are never stripped —
OpenRouter lists ``model`` and ``model:batch`` as independent entries, so
stripping would collide two entries onto one key. Lookup is two-level exact:
the raw id first, then the full entry id (``{provider}/{raw_id}``). When
several entries normalize onto one key, that whole key is omitted (宁缺勿错 —
wrong metadata is worse than no metadata). An id that misses against a loaded
catalog is logged once internally so naming drift stays visible (R7).

KTD4 — ingest is type-validated: the two integers must be positive and inside
a sane ceiling, the modality fields must be string arrays; anything else is
dropped field-by-field, and a malformed catalog response is a fetch failure.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

CATALOG_URL = "https://openrouter.ai/api/v1/models"
DEFAULT_TTL = 24 * 3600.0  # one whole-catalog fetch per TTL window
FAILURE_COOLDOWN = 300.0  # after a failed fetch, no retry for 5 minutes
MAX_AGE = 7 * 24 * 3600.0  # stale-on-error ceiling: older than 7d = absent
MAX_CATALOG_BYTES = 32 * 1024 * 1024

_CAPABILITY_INT_CEILING = 100_000_000
_MAX_MODALITIES = 32
_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

CAPABILITY_FIELDS = (
    "context_length",
    "max_output_tokens",
    "input_modalities",
    "output_modalities",
)

_VENDOR_ALIASES = {"xai": "x-ai"}
_VERSION_SEPARATOR = re.compile(r"v-(?=\d)")


def _normalize_key(model_id: str) -> str:
    """KTD2 normalization: lowercase, vendor aliases, version-separator fold."""
    key = model_id.strip().lower()
    key = _VERSION_SEPARATOR.sub("v", key)  # "mimo-v-2.5" -> "mimo-v2.5"
    if "/" in key:
        vendor, rest = key.split("/", 1)
        return f"{_VENDOR_ALIASES.get(vendor, vendor)}/{rest}"
    return _VENDOR_ALIASES.get(key, key)


def _as_capability_int(value: Any) -> int | None:
    """A positive int within a sane ceiling, else None (bool is not an int)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0 or value > _CAPABILITY_INT_CEILING:
        return None
    return value


def _as_modality_list(value: Any) -> list[str] | None:
    """A bounded list of strings, else None. New enum values pass untouched."""
    if not isinstance(value, list) or len(value) > _MAX_MODALITIES:
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return list(value)


def upstream_passthrough(entry: dict[str, Any]) -> dict[str, Any]:
    """R5 whitelist: same name + right type passes through, nothing else.

    Near-synonym keys (``max_tokens``, ``context_window``, ...) are NOT
    mapped; a field absent here falls through to the catalog backfill.
    """
    out: dict[str, Any] = {}
    context_length = _as_capability_int(entry.get("context_length"))
    if context_length is not None:
        out["context_length"] = context_length
    max_output = _as_capability_int(entry.get("max_output_tokens"))
    if max_output is not None:
        out["max_output_tokens"] = max_output
    input_modalities = _as_modality_list(entry.get("input_modalities"))
    if input_modalities is not None:
        out["input_modalities"] = input_modalities
    output_modalities = _as_modality_list(entry.get("output_modalities"))
    if output_modalities is not None:
        out["output_modalities"] = output_modalities
    return out


def _catalog_entry(entry: Any) -> tuple[str, dict[str, Any]] | None:
    """Validate one catalog entry; drop it unless it has a usable id (KTD4)."""
    if not isinstance(entry, dict):
        return None
    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not entry_id.strip():
        return None

    cap: dict[str, Any] = {}
    context_length = _as_capability_int(entry.get("context_length"))
    if context_length is not None:
        cap["context_length"] = context_length

    top_provider = entry.get("top_provider")
    if isinstance(top_provider, dict):
        max_output = _as_capability_int(top_provider.get("max_completion_tokens"))
        if max_output is not None:
            cap["max_output_tokens"] = max_output

    architecture = entry.get("architecture")
    if isinstance(architecture, dict):
        input_modalities = _as_modality_list(architecture.get("input_modalities"))
        if input_modalities is not None:
            cap["input_modalities"] = input_modalities
        output_modalities = _as_modality_list(architecture.get("output_modalities"))
        if output_modalities is not None:
            cap["output_modalities"] = output_modalities

    return entry_id, cap


class _KeyIndex:
    """Normalized key → capability, with whole-key omission on collision."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}
        self._conflicts: set[str] = set()

    def add(self, key: str, cap: dict[str, Any]) -> None:
        if key in self._conflicts:
            return
        if key in self._entries:
            # Two entries normalized onto one key: the whole key is omitted
            # (宁缺勿错) rather than guessed down to one of them.
            del self._entries[key]
            self._conflicts.add(key)
            return
        self._entries[key] = cap

    def freeze(self) -> dict[str, dict[str, Any]]:
        return dict(self._entries)


def _build_indexes(payload: Any) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]] | None:
    """Parse a catalog payload into (raw-id index, full-entry-id index).

    Returns None for a malformed payload — that is a fetch failure, not an
    empty catalog. Bad entries and bad fields are dropped individually.
    """
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, list):
        return None

    raw_index = _KeyIndex()
    full_index = _KeyIndex()
    for entry in data:
        parsed = _catalog_entry(entry)
        if parsed is None:
            continue
        entry_id, cap = parsed
        raw_id = entry_id.split("/", 1)[1] if "/" in entry_id else entry_id
        raw_index.add(_normalize_key(raw_id), cap)
        full_index.add(_normalize_key(entry_id), cap)
    return raw_index.freeze(), full_index.freeze()


def fetch_catalog() -> Any:
    """One GET of the pinned OpenRouter catalog; None on any failure.

    HTTPS is pinned to openrouter.ai and cross-origin redirects are refused
    (KTD5 risk containment) — a redirect target outside
    ``https://openrouter.ai`` is a failure, not a hop. Oversized responses and
    malformed JSON are failures too; the caller keeps whatever table it has.
    """
    try:
        with httpx.Client(
            timeout=httpx.Timeout(10.0, connect=5.0), follow_redirects=False
        ) as client:
            url = CATALOG_URL
            for _ in range(_MAX_REDIRECTS + 1):
                resp = client.get(url)
                if resp.status_code in _REDIRECT_STATUSES:
                    location = resp.headers.get("location")
                    if not location:
                        return None
                    url = urljoin(url, location)
                    target = httpx.URL(url)
                    if target.scheme != "https" or (target.host or "").lower() != "openrouter.ai":
                        logger.warning(
                            "OpenRouter catalog redirect refused (cross-origin): %s", url
                        )
                        return None
                    continue
                if resp.status_code != 200:
                    logger.warning("OpenRouter catalog returned status %d", resp.status_code)
                    return None
                if len(resp.content) > MAX_CATALOG_BYTES:
                    logger.warning(
                        "OpenRouter catalog too large (%d bytes)", len(resp.content)
                    )
                    return None
                return resp.json()
            logger.warning("OpenRouter catalog gave up after %d redirects", _MAX_REDIRECTS)
            return None
    except Exception as e:
        logger.warning("OpenRouter catalog fetch failed: %s", e)
        return None


class ModelCapabilitiesCatalog:
    """Whole-catalog cache for model capability metadata (KTD1).

    Cache states: ``fresh`` / ``stale`` (usable, serving while revalidating or
    on error) / ``absent`` (never fetched) / ``failed`` (fetched at least once
    but there is no usable table). Lookups against absent/failed return empty
    capabilities; both cases trigger a background refresh subject to
    single-flight and the failure cooldown.
    """

    def __init__(
        self,
        *,
        fetcher: Any = None,
        ttl: float = DEFAULT_TTL,
        failure_cooldown: float = FAILURE_COOLDOWN,
        max_age: float = MAX_AGE,
    ) -> None:
        self._fetcher = fetcher
        self._ttl = ttl
        self._failure_cooldown = failure_cooldown
        self._max_age = max_age
        self._lock = threading.Lock()
        self._raw_index: dict[str, dict[str, Any]] = {}
        self._full_index: dict[str, dict[str, Any]] = {}
        self._fetched_at: float | None = None
        self._last_failure_at: float | None = None
        self._refresh_in_flight = False
        self._refresh_thread: threading.Thread | None = None
        self._miss_logged: set[str] = set()

    # ------------------------------------------------------------------
    # Query path — synchronous, pure-local, never waits on the network
    # ------------------------------------------------------------------

    def lookup(self, model_id: str) -> dict[str, Any]:
        """Capability fields for one model id, or {} when unknown/unavailable.

        KTD1: never blocks. TTL-expired and cache-less calls trigger a
        background refresh and answer immediately from whatever table exists.
        """
        if not isinstance(model_id, str):
            return {}

        trigger = False
        result: dict[str, Any] = {}
        log_miss = False
        with self._lock:
            now = time.time()
            if self._fetched_at is not None and (now - self._fetched_at) <= self._max_age:
                cap = self._match_locked(model_id)
                if cap is None:
                    if model_id not in self._miss_logged:
                        self._miss_logged.add(model_id)
                        log_miss = True
                else:
                    result = dict(cap)
                if (now - self._fetched_at) >= self._ttl:
                    trigger = True
            else:
                # Absent, failed, or over-age (R8: >7d counts as absent).
                trigger = True

        if log_miss:
            logger.info("model capability lookup miss for id '%s'", model_id)
        if trigger:
            self._trigger_refresh()
        return result

    def _match_locked(self, model_id: str) -> dict[str, Any] | None:
        """KTD2 two-level exact match: raw id first, then full entry id."""
        raw_id = model_id.split("/", 1)[1] if "/" in model_id else model_id
        cap = self._raw_index.get(_normalize_key(raw_id))
        if cap is None:
            cap = self._full_index.get(_normalize_key(model_id))
        return cap

    def state(self) -> str:
        """One of: fresh / stale / absent / failed."""
        with self._lock:
            return self._state_locked(time.time())

    def _state_locked(self, now: float) -> str:
        if self._fetched_at is not None:
            age = now - self._fetched_at
            if age <= self._max_age:
                return "fresh" if age < self._ttl else "stale"
        return "failed" if self._last_failure_at is not None else "absent"

    # ------------------------------------------------------------------
    # Refresh path — background only, single-flight + failure cooldown
    # ------------------------------------------------------------------

    def warm_up(self) -> None:
        """Cold-start prefetch; call once at process start (KTD1)."""
        self._trigger_refresh()

    def wait_for_refresh(self, timeout: float = 5.0) -> None:
        """Join the in-flight background refresh if there is one (tests/ops)."""
        with self._lock:
            thread = self._refresh_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)

    def _trigger_refresh(self) -> None:
        with self._lock:
            now = time.time()
            if self._refresh_in_flight:
                return
            if (
                self._last_failure_at is not None
                and (now - self._last_failure_at) < self._failure_cooldown
            ):
                return
            self._refresh_in_flight = True
            thread = threading.Thread(
                target=self._refresh_worker,
                name="otel-agent-model-capabilities",
                daemon=True,
            )
            self._refresh_thread = thread
        thread.start()

    def _refresh_worker(self) -> None:
        ok = False
        try:
            fetcher = self._fetcher if self._fetcher is not None else fetch_catalog
            payload = fetcher()
            built = _build_indexes(payload) if payload is not None else None
            if built is not None:
                raw_index, full_index = built
                with self._lock:
                    self._raw_index = raw_index
                    self._full_index = full_index
                    self._fetched_at = time.time()
                    self._last_failure_at = None
                ok = True
        except Exception as e:
            logger.warning("model capability catalog refresh failed: %s", e)
        finally:
            with self._lock:
                if not ok:
                    self._last_failure_at = time.time()
                self._refresh_in_flight = False


# ----------------------------------------------------------------------
# Process-wide instance. The server warms it up at process start; lookup()
# is what the /v1/models assembly calls per entry.
# ----------------------------------------------------------------------

_catalog = ModelCapabilitiesCatalog()


def lookup(model_id: str) -> dict[str, Any]:
    """Capability fields for one model id from the process-wide catalog."""
    return _catalog.lookup(model_id)


def warm_up() -> None:
    """Cold-start prefetch of the process-wide catalog (KTD1)."""
    _catalog.warm_up()

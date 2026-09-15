"""Sidecar OAuth vault for SuperGrok / xAI subscription tokens."""
from __future__ import annotations

import base64
import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import httpx

from otel_agent.config import AUTH_CODEX_OAUTH, AUTH_XAI_OAUTH, Provider, auth_source

DEFAULT_VAULT_PATH = Path.home() / ".otel-agent" / "auth.json"
XAI_OAUTH_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_OAUTH_DISCOVERY_URL = "https://auth.x.ai/.well-known/openid-configuration"
XAI_OAUTH_TOKEN_URL = "https://auth.x.ai/oauth2/token"
XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 3600
CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 300
DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"

#: Appended to a grant's own ``iss`` when neither the source data nor the
#: source declaration names a token endpoint. The host comes entirely from the
#: credential, which is what keeps this a derivation rather than the vendor
#: default KTD4 forbids.
OAUTH_TOKEN_PATH = "/oauth/token"

#: How long a writer waits for the cross-process vault lock. Long enough to
#: outlast a slow token exchange, short enough that a wedged holder surfaces as
#: an error instead of a hung gateway.
_LOCK_TIMEOUT_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.02


class AuthError(Exception):
    """Raised when a SuperGrok grant is missing or cannot be refreshed.

    ``provider`` names the subscription the failure is about, when the raiser
    knows it. It exists so the HTTP layer can answer with that subscription's
    status instead of a message the client has to parse (R12).
    """

    def __init__(self, message: str, *, provider: str = "") -> None:
        super().__init__(message)
        self.provider = provider


@dataclass(frozen=True)
class RefreshPolicy:
    """Refresh rules declared once per auth mode.

    ``skew_seconds`` is how long before expiry a token is refreshed. It is
    declared per mode rather than shared: a provider whose access token lives
    no longer than another mode's skew would otherwise refresh on every single
    request, spending the one-time refresh token each time and turning the
    crash window R6 protects from a rare event into a per-request one.
    """

    skew_seconds: int

    token_endpoint: str = ""
    """The one endpoint a refresh token may be sent to for this mode.

    Empty means the endpoint is credential-specific: it must be recorded on
    the vault entry itself and is then used verbatim. Either way there is no
    discovery refetch and no vendor-default fallback (KTD4)."""


#: Auth mode -> refresh declaration. A mode that is not here cannot be
#: refreshed; the credential is served as-is or the caller is told to re-adopt.
REFRESH_POLICIES: dict[str, RefreshPolicy] = {
    AUTH_XAI_OAUTH: RefreshPolicy(
        skew_seconds=XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS,
        token_endpoint=XAI_OAUTH_TOKEN_URL,
    ),
    # The Codex token endpoint is not a vendor default we may hardcode: it is
    # read off the adopted grant and recorded on the entry (see U3).
    AUTH_CODEX_OAUTH: RefreshPolicy(skew_seconds=CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS),
}


def default_vault_path() -> Path:
    override = os.environ.get("OTEL_AGENT_AUTH_PATH", "").strip()
    return Path(override).expanduser() if override else DEFAULT_VAULT_PATH


def _jwt_claims(token: str) -> dict[str, Any]:
    """Decode a JWT payload. Unverified on purpose: the token is the credential
    this process already holds, and its claims are read for routing metadata
    (expiry, issuer, client id), never for trust."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    try:
        pad = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _jwt_claim(token: str, *path: str) -> Any:
    """Read one claim out of a JWT payload, following a nested path.

    ``("exp",)`` reads a top-level claim; a longer path descends into nested
    objects, which is how this vendor namespaces its subscription metadata.
    The claims are unverified, exactly as in ``_jwt_claims``.
    """
    node: Any = _jwt_claims(token)
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _jwt_exp(token: str) -> int | None:
    exp = _jwt_claim(token, "exp")
    return int(exp) if isinstance(exp, (int, float)) else None


#: Where a Codex grant names its subscription tier (R11's 「档位」). The vendor
#: puts it under a URL-shaped claim rather than a top-level one, so the path is
#: declared here instead of being sniffed for by claim name.
PLAN_TYPE_CLAIM = ("https://api.openai.com/auth", "chatgpt_plan_type")


def plan_type_from_access_token(access_token: str) -> str:
    """The subscription tier the token itself names, or '' when it names none.

    Read off the credential rather than stored beside it, so no refresh can
    leave a stale tier behind: whatever the live token claims is the answer.
    """
    value = _jwt_claim(access_token, *PLAN_TYPE_CLAIM)
    return str(value).strip() if isinstance(value, str) else ""


def _iso_utc(timestamp: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


def token_endpoint_from_claims(claims: dict[str, Any]) -> str:
    """Derive the token endpoint a grant's refresh token may be presented to.

    Read off the grant's own ``iss`` so the host follows the credential rather
    than a hardcoded vendor default (KTD4). An issuer that is not an absolute
    https URL yields nothing: a caller that cannot derive an endpoint must
    refuse rather than guess one.
    """
    issuer = str(claims.get("iss") or "").strip().rstrip("/")
    parsed = urlparse(issuer)
    if parsed.scheme != "https" or not parsed.netloc:
        return ""
    return issuer + OAUTH_TOKEN_PATH


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"providers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"providers": {}}
    if not isinstance(data, dict):
        return {"providers": {}}
    providers = data.get("providers")
    if not isinstance(providers, dict):
        data["providers"] = {}
    return data


def _fsync_directory(path: Path) -> None:
    """Make the rename itself durable (KTD3).

    fsync on the new file only guarantees its contents; the directory entry
    that now points at it survives a power loss only once the directory is
    synced too.
    """
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".auth-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


@contextmanager
def _vault_lock(vault: Path, *, timeout: float | None = None) -> Iterator[None]:
    """Hold the vault's exclusive cross-process lock (KTD2).

    The lock is taken on a *sibling* file that ``os.replace`` never touches:
    locking the vault itself would let two processes each "hold" a lock on
    their own inode. ``flock`` is released by the OS when the holder dies, so a
    killed refresh cannot leave an ownerless lock behind. Each acquisition
    opens its own file description, so threads contend with each other exactly
    as separate processes do.
    """
    lock_path = vault.with_name(vault.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    limit = _LOCK_TIMEOUT_SECONDS if timeout is None else timeout
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + limit
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise AuthError(
                        f"Timed out after {limit:.1f}s waiting for the vault lock at "
                        f"{lock_path}; another otel-agent process is holding it."
                    )
                time.sleep(_LOCK_POLL_SECONDS)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def save_grant(
    provider_name: str,
    tokens: dict[str, Any],
    *,
    auth: str,
    discovery: dict[str, Any] | None = None,
    client_id: str = "",
    imported_from: str = "",
    path: Path | None = None,
) -> None:
    """Persist a copied grant into the sidecar vault.

    *auth* is the writer's declared credential source; it is recorded on the
    entry so refresh policy is read from the declaration rather than inferred
    from the provider name. The entry is merged into, not replaced: fields this
    caller does not set (status written by the refresh path, plan claims, a
    token endpoint recorded at import time) survive.

    *client_id* is the one a refresh presents; it is recorded with the
    credential rather than assumed, because a mode whose token endpoint is
    credential-specific has nowhere else to get it from.

    Adopting a grant is also what clears an interrupted-refresh marker: the
    ambiguity that marker records is resolved by the new refresh token.
    """
    vault = path or default_vault_path()
    access = str(tokens.get("access_token", "") or "").strip()
    refresh = str(tokens.get("refresh_token", "") or "").strip()
    if not access or not refresh:
        raise AuthError("Grant is missing access_token or refresh_token.")
    expires_at = _jwt_exp(access)
    if expires_at is None:
        expires_in = tokens.get("expires_in")
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            expires_at = int(time.time()) + int(expires_in)
        else:
            expires_at = 0
    with _vault_lock(vault):
        data = _load(vault)
        providers: dict[str, Any] = data.setdefault("providers", {})
        prior = providers.get(provider_name)
        entry: dict[str, Any] = dict(prior) if isinstance(prior, dict) else {}
        entry["auth"] = auth
        entry["tokens"] = {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": str(tokens.get("token_type") or "Bearer"),
            "expires_at": expires_at,
        }
        if discovery or not isinstance(entry.get("discovery"), dict):
            entry["discovery"] = discovery or {}
        if client_id or "client_id" not in entry:
            entry["client_id"] = client_id
        if imported_from or "imported_from" not in entry:
            entry["imported_from"] = imported_from
        entry.pop("refresh_in_flight", None)
        providers[provider_name] = entry
        _atomic_write(vault, data)


def get_status(provider_name: str = "xai", *, path: Path | None = None) -> dict[str, Any]:
    """The current state of one subscription (R11).

    Four answers, and nothing that would require a network round trip to give:

    ``available``
        Whether the gateway holds a credential it can present. A grant that is
        missing, incomplete, or left unresolved mid-refresh is not available.
        Whether the last refresh *worked* is the ``last_result`` half of the
        answer, deliberately not folded in here: deciding it would mean
        attempting a refresh, which is the caller's business.
    ``plan``
        The tier the access token itself names, or '' when it names none.
    ``expires_at``
        When the access token stops being usable, in epoch seconds.
    ``last_result``
        How the last refresh attempt ended — ``{"at", "ok", "detail"}`` — or
        None on a grant the gateway has never tried to refresh.
    """
    vault = path or default_vault_path()
    entry = _load(vault).get("providers", {}).get(provider_name)
    if not isinstance(entry, dict):
        return {
            "logged_in": False,
            "available": False,
            "path": str(vault),
            "imported_from": "",
            "plan": "",
            "expires_at": None,
            "last_result": None,
            "last_refresh": "",
        }
    raw_tokens = entry.get("tokens")
    tokens: dict[str, Any] = raw_tokens if isinstance(raw_tokens, dict) else {}
    access = str(tokens.get("access_token", "") or "").strip()
    refresh = str(tokens.get("refresh_token", "") or "").strip()
    logged_in = bool(access and refresh)
    result = entry.get("last_refresh_result")
    return {
        "logged_in": logged_in,
        "available": logged_in and not entry.get("refresh_in_flight"),
        "path": str(vault),
        "imported_from": entry.get("imported_from") or "",
        "plan": plan_type_from_access_token(access),
        "expires_at": tokens.get("expires_at"),
        "last_result": dict(result) if isinstance(result, dict) else None,
        "last_refresh": str(entry.get("last_refresh") or ""),
    }


def _needs_refresh(entry: dict[str, Any]) -> bool:
    """Whether *entry*'s access token must be refreshed before it is used.

    An expiry that cannot be determined is *not* treated as "never expires":
    a token whose lifetime cannot be read is refreshed rather than served
    forever. The skew comes from the entry's declared auth mode, never from a
    shared constant (a mode whose tokens live no longer than another mode's
    skew would otherwise refresh on every request).
    """
    raw_tokens = entry.get("tokens")
    tokens: dict[str, Any] = raw_tokens if isinstance(raw_tokens, dict) else {}
    access = str(tokens.get("access_token", "") or "").strip()
    if not access:
        return True
    policy = REFRESH_POLICIES.get(str(entry.get("auth") or ""))
    skew = policy.skew_seconds if policy else 0
    expires_at = tokens.get("expires_at")
    if not isinstance(expires_at, (int, float)) or expires_at <= 0:
        expires_at = _jwt_exp(access) or 0
    if expires_at <= 0:
        return True
    return time.time() >= (expires_at - skew)


@dataclass(frozen=True)
class _RefreshTarget:
    """Everything a refresh needs, resolved and validated up front."""

    endpoint: str
    client_id: str
    refresh_token: str
    mode: str


def _refresh_target(entry: dict[str, Any]) -> _RefreshTarget:
    """Resolve where this credential's refresh token may be presented (KTD4).

    The endpoint is only ever the one declared for the auth mode, or — for a
    mode whose endpoint is credential-specific — the one recorded on the entry
    itself. It is never re-derived from live discovery and never a hardcoded
    vendor default, and the criterion is exact equality rather than a host
    suffix (``evilx.ai`` ends with ``x.ai``).
    """
    mode = str(entry.get("auth") or "")
    policy = REFRESH_POLICIES.get(mode)
    if policy is None:
        raise AuthError(
            f"No refresh is declared for auth mode '{mode}'. The credential must be re-adopted."
        )
    raw_tokens = entry.get("tokens")
    tokens: dict[str, Any] = raw_tokens if isinstance(raw_tokens, dict) else {}
    refresh = str(tokens.get("refresh_token", "") or "").strip()
    if not refresh:
        raise AuthError(f"The '{mode}' grant has no refresh_token. The credential must be re-adopted.")
    raw_discovery = entry.get("discovery")
    discovery: dict[str, Any] = raw_discovery if isinstance(raw_discovery, dict) else {}
    recorded = str(discovery.get("token_endpoint", "") or "").strip()
    if not recorded:
        raise AuthError(
            f"The '{mode}' grant records no token endpoint, so its refresh token has "
            f"nowhere to go: refusing to fall back to a vendor default. "
            f"The credential must be re-adopted."
        )
    if policy.token_endpoint and recorded != policy.token_endpoint:
        raise AuthError(
            f"The '{mode}' grant records token endpoint '{recorded}', which is not the "
            f"endpoint declared for this auth mode: refusing to send the refresh token "
            f"there. The credential must be re-adopted."
        )
    client_id = str(entry.get("client_id") or "").strip()
    if not client_id and mode == AUTH_XAI_OAUTH:
        client_id = XAI_OAUTH_CLIENT_ID
    if not client_id:
        raise AuthError(f"The '{mode}' grant records no client_id. The credential must be re-adopted.")
    return _RefreshTarget(
        endpoint=policy.token_endpoint or recorded,
        client_id=client_id,
        refresh_token=refresh,
        mode=mode,
    )


def _begin_refresh(entry: dict[str, Any]) -> dict[str, Any]:
    """Record the intent to refresh, durably, before the token is presented (R6).

    After this point a crash is indistinguishable from "the refresh token was
    consumed by the exchange": without the marker the on-disk state looks
    exactly like "no refresh ever ran", and AE3's identification would have
    nothing to go on.
    """
    generation = int(entry.get("generation") or 0) + 1
    updated = dict(entry)
    updated["generation"] = generation
    updated["refresh_in_flight"] = {
        "generation": generation,
        "started_at": time.time(),
    }
    return updated


def _post_refresh(target: _RefreshTarget) -> dict[str, Any]:
    """Present the refresh token to the one endpoint it may be sent to."""
    resp = httpx.post(
        target.endpoint,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        data={
            "grant_type": "refresh_token",
            "client_id": target.client_id,
            "refresh_token": target.refresh_token,
        },
        timeout=20.0,
    )
    if resp.status_code != 200:
        raise AuthError(
            f"OAuth refresh of the '{target.mode}' grant failed (HTTP {resp.status_code}). "
            f"The credential must be re-adopted."
        )
    payload = resp.json()
    if not isinstance(payload, dict):
        raise AuthError(
            f"OAuth refresh of the '{target.mode}' grant returned no JSON object. "
            f"The credential must be re-adopted."
        )
    return payload


def _finish_refresh(entry: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Commit the new pair and clear the in-flight marker.

    A response without a new refresh token is an error, never a silent reuse of
    the token the exchange has just consumed.
    """
    mode = str(entry.get("auth") or "")
    access = str(payload.get("access_token", "") or "").strip()
    if not access:
        raise AuthError(
            f"OAuth refresh of the '{mode}' grant returned no access_token. "
            f"The credential must be re-adopted."
        )
    new_refresh = str(payload.get("refresh_token", "") or "").strip()
    if not new_refresh:
        raise AuthError(
            f"OAuth refresh of the '{mode}' grant returned no new refresh_token: the "
            f"previous one may already be consumed, so it is not reused. "
            f"The credential must be re-adopted."
        )
    expires_at = _jwt_exp(access)
    if expires_at is None:
        expires_in = payload.get("expires_in")
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            expires_at = int(time.time()) + int(expires_in)
        else:
            expires_at = 0
    updated = dict(entry)
    updated["tokens"] = {
        "access_token": access,
        "refresh_token": new_refresh,
        "token_type": str(payload.get("token_type") or "Bearer"),
        "expires_at": expires_at,
    }
    updated.pop("refresh_in_flight", None)
    return updated


def _record_refresh_result(entry: dict[str, Any], *, ok: bool, detail: str = "") -> dict[str, Any]:
    """Record how a refresh attempt ended, on the entry it was made for (R11).

    Written for a refusal as well as for a failed exchange: "refused, because
    the credential records no client_id" is precisely the diagnosis the status
    surface exists to hand the operator, and it is otherwise only in a message
    nobody kept. ``last_refresh`` is advanced only on success, so a second
    writer can be recognised by comparing timestamps rather than attempts.
    """
    now = time.time()
    updated = dict(entry)
    updated["last_refresh_result"] = {"at": now, "ok": bool(ok), "detail": detail}
    if ok:
        updated["last_refresh"] = _iso_utc(now)
    return updated


def _marker_detail(marker: Any) -> str:
    """Describe an interrupted-refresh marker for the operator."""
    if not isinstance(marker, dict):
        return ""
    parts = []
    generation = marker.get("generation")
    if isinstance(generation, int):
        parts.append(f"generation {generation}")
    started_at = marker.get("started_at")
    if isinstance(started_at, (int, float)):
        parts.append("started " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started_at)))
    return f" ({', '.join(parts)})" if parts else ""


def resolve_bearer(provider: Provider, *, path: Path | None = None, force: bool = False) -> str:
    """Return a live Bearer secret for *provider*.

    Blocking: it holds the cross-process vault lock and may refresh the
    credential over the network. Async callers must go through
    ``provider_utils.resolve_bearer_async`` so that a refresh never runs on the
    event loop (KTD1).

    *force* refreshes a token that still looks valid. Adoption is the caller
    that needs it (F1): on a single-use rotating chain the point of adopting is
    to be the writer that spends the old refresh token first, not to wait for
    the copied access token to age.
    """
    source = auth_source(provider.auth)
    if source is None or not source.vault_backed:
        if provider.api_key:
            return provider.api_key
        raise AuthError(f"Provider '{provider.name}' has no api_key.")

    vault = path or default_vault_path()
    name = provider.name
    with _vault_lock(vault):
        data = _load(vault)
        entry = data.get("providers", {}).get(name)
        if not isinstance(entry, dict):
            if provider.api_key:
                return provider.api_key
            raise AuthError(
                f"No subscription grant for '{name}' in the vault. "
                f"Run: otel-agent auth login",
                provider=name,
            )
        marker = entry.get("refresh_in_flight")
        if marker:
            raise AuthError(
                f"An interrupted refresh left '{name}' in an ambiguous state"
                f"{_marker_detail(marker)}: its refresh token may already have been "
                f"consumed, so it is not presented again automatically. "
                f"The credential must be re-adopted.",
                provider=name,
            )
        if force or _needs_refresh(entry):
            # Validate where the token may go *before* recording any intent: a
            # credential that cannot be refreshed is not an ambiguous one.
            try:
                target = _refresh_target(entry)
                entry = _begin_refresh(entry)
                data["providers"][name] = entry
                _atomic_write(vault, data)
                payload = _post_refresh(target)
                entry = _finish_refresh(entry, payload)
            except AuthError as exc:
                # A refusal is a result too, and the only record of it the
                # operator can read afterwards (R11). It is written before the
                # error leaves, while the lock that guards the entry is held.
                entry = _record_refresh_result(entry, ok=False, detail=str(exc))
                data["providers"][name] = entry
                _atomic_write(vault, data)
                raise AuthError(str(exc), provider=name) from exc
            entry = _record_refresh_result(entry, ok=True)
            data["providers"][name] = entry
            _atomic_write(vault, data)
        raw_tokens = entry.get("tokens")
        tokens: dict[str, Any] = raw_tokens if isinstance(raw_tokens, dict) else {}
        access = str(tokens.get("access_token", "") or "").strip()
        if not access:
            raise AuthError(
                f"Subscription grant for '{name}' has no access_token.", provider=name
            )
        return access


@dataclass(frozen=True)
class GrantSource:
    """One sibling CLI's store, declared rather than branched on (D2).

    Adopting a grant is a lookup in a table of these: the file, the pointers
    into it, the provider the grant lands under, and whatever the store cannot
    supply are all declared here. The owner's file is read and never written.
    """

    label: str
    """Recorded as the vault entry's ``imported_from``."""

    path: Path
    """The owner CLI's credential store."""

    pointers: tuple[tuple[str, ...], ...]
    """Tried in order; the first node holding a complete token pair wins.

    The order matters and is declared per source: it decides which shape's
    ``base_url`` and ``discovery`` a grant is read from.
    """

    provider: str
    """Provider name the grant is stored under, and the row written to config."""

    auth: str
    """Declared credential source, recorded on the vault entry."""

    base_url: str = ""
    """Upstream base_url for the provider config row, when the store has none."""

    token_endpoint: str = ""
    """Declared token endpoint. Empty means the store does not carry one and it
    is read off the adopted grant's own claims instead (see ``adopt_grant``)."""

    client_id: str = ""
    """Declared client_id, under the same rule as ``token_endpoint``."""


@dataclass(frozen=True)
class AdoptedGrant:
    """A grant lifted out of a sibling store, before it is written anywhere."""

    tokens: dict[str, Any]
    discovery: dict[str, Any]
    base_url: str = ""


@dataclass(frozen=True)
class Adoption:
    """What adopting a grant produced, for the caller to report."""

    base_url: str
    bearer: str


def _walk(node: Any, pointer: tuple[str, ...]) -> Any:
    for key in pointer:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _grant_from_node(node: dict[str, Any]) -> AdoptedGrant | None:
    """Read one candidate node, in either shape a store may present.

    A ``providers`` entry keeps the pair under ``tokens`` and its discovery
    document beside it; a ``credential_pool`` entry keeps the pair flat and its
    ``base_url`` beside it. Only the node that actually supplied the pair is
    read for either.
    """
    raw_tokens = node.get("tokens")
    tokens: dict[str, Any] = raw_tokens if isinstance(raw_tokens, dict) else node
    access = str(tokens.get("access_token", "") or "").strip()
    refresh = str(tokens.get("refresh_token", "") or "").strip()
    if not access or not refresh:
        return None
    raw_discovery = node.get("discovery")
    return AdoptedGrant(
        tokens={
            "access_token": access,
            "refresh_token": refresh,
            "token_type": str(tokens.get("token_type") or "Bearer"),
        },
        discovery=dict(raw_discovery) if isinstance(raw_discovery, dict) else {},
        base_url=str(node.get("base_url", "") or "").strip(),
    )


def extract_grant(store: dict[str, Any], source: GrantSource) -> AdoptedGrant | None:
    """Pull a usable grant out of an already-parsed sibling store (pure)."""
    for pointer in source.pointers:
        node = _walk(store, pointer)
        if isinstance(node, dict):
            candidates: list[Any] = [node]
        elif isinstance(node, list):
            candidates = node
        else:
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            grant = _grant_from_node(candidate)
            if grant is not None:
                return grant
    return None


def read_owner_last_refresh(source: GrantSource) -> str:
    """When the owner CLI itself last refreshed the grant *source* names.

    Read-only, and best-effort by design: most machines have no sibling CLI
    installed, and a store that cannot be read says nothing about a second
    writer. Both cases yield '' rather than an error, so a caller can ask this
    on every machine without guarding it.
    """
    try:
        store = json.loads(source.path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(store, dict):
        return ""
    for pointer in source.pointers:
        node = _walk(store, pointer)
        for candidate in (node if isinstance(node, list) else [node]):
            if not isinstance(candidate, dict):
                continue
            value = candidate.get("last_refresh")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def read_grant_source(source: GrantSource) -> AdoptedGrant:
    """Read *source*'s store and extract its grant.

    The owner CLI's file is opened for reading only — a refresh writes the
    vault and nothing else (R3).
    """
    try:
        store = json.loads(source.path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AuthError(
            f"{source.path} does not exist, so the {source.label} CLI is not signed in "
            f"on this machine."
        ) from exc
    except (OSError, ValueError) as exc:
        raise AuthError(f"{source.path} is unreadable: {exc}") from exc
    if not isinstance(store, dict):
        raise AuthError(f"{source.path} does not hold a JSON object.")
    grant = extract_grant(store, source)
    if grant is None:
        raise AuthError(f"{source.path} holds no {source.provider} grant.")
    return grant


def _credential_metadata(grant: AdoptedGrant, source: GrantSource) -> tuple[dict[str, Any], str]:
    """The token endpoint and client_id a later refresh will present (KTD4).

    Neither is in the store: its ``base_url`` is the API host, while the token
    host is another one entirely. Both are read off the adopted grant's own
    claims, so they follow the credential rather than a vendor default.
    """
    claims = _jwt_claims(str(grant.tokens.get("access_token", "") or ""))
    discovery = dict(grant.discovery)
    if not str(discovery.get("token_endpoint") or "").strip():
        endpoint = source.token_endpoint or token_endpoint_from_claims(claims)
        if not endpoint:
            raise AuthError(
                f"The {source.provider} grant in {source.path} records no token endpoint and "
                f"its access token names no usable issuer, so a refresh would have nowhere "
                f"to go: refusing to fall back to a vendor default."
            )
        discovery["token_endpoint"] = endpoint
    client_id = source.client_id or str(claims.get("client_id") or "").strip()
    if not client_id:
        raise AuthError(
            f"The {source.provider} grant in {source.path} records no client_id and its "
            f"access token names none, so its refresh token could not be presented."
        )
    return discovery, client_id


def adopt_grant(source: GrantSource, *, path: Path | None = None) -> Adoption:
    """Adopt *source*'s grant and take over the chain (R3 / F1).

    Three steps, in this order and for a reason:

    1. The sibling's store is read — never written — and its pair copied into
       the vault.
    2. The token endpoint and client_id are recorded on the entry from the
       adopted grant's own claims. Without them the first refresh is refused
       outright (KTD4), so an adoption that skipped this would hand the gateway
       a credential it could not keep alive.
    3. The gateway refreshes once, immediately. On a single-use rotating chain
       this is what makes it the only writer: whoever presents the refresh
       token first consumes it, and the sibling's copy is then dead. Waiting
       for the copied access token to near expiry would leave the sibling a
       window to refresh first — and a loser that presents a revoked copy takes
       the whole family down with it.
    """
    grant = read_grant_source(source)
    discovery, client_id = _credential_metadata(grant, source)
    vault = path or default_vault_path()
    save_grant(
        source.provider,
        grant.tokens,
        auth=source.auth,
        discovery=discovery,
        client_id=client_id,
        imported_from=source.label,
        path=vault,
    )
    base_url = grant.base_url or source.base_url
    provider = Provider(name=source.provider, base_url=base_url, api_key="", auth=source.auth)
    return Adoption(base_url=base_url, bearer=resolve_bearer(provider, path=vault, force=True))

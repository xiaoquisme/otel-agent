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

import httpx

from otel_agent.config import AUTH_CODEX_OAUTH, AUTH_XAI_OAUTH, Provider, auth_source

DEFAULT_VAULT_PATH = Path.home() / ".otel-agent" / "auth.json"
XAI_OAUTH_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_OAUTH_DISCOVERY_URL = "https://auth.x.ai/.well-known/openid-configuration"
XAI_OAUTH_TOKEN_URL = "https://auth.x.ai/oauth2/token"
XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 3600
CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 300
DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"

#: How long a writer waits for the cross-process vault lock. Long enough to
#: outlast a slow token exchange, short enough that a wedged holder surfaces as
#: an error instead of a hung gateway.
_LOCK_TIMEOUT_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.02


class AuthError(Exception):
    """Raised when a SuperGrok grant is missing or cannot be refreshed."""


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


def _jwt_exp(token: str) -> int | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None
    try:
        pad = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    except Exception:
        return None
    exp = payload.get("exp")
    return int(exp) if isinstance(exp, (int, float)) else None


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
    imported_from: str = "",
    path: Path | None = None,
) -> None:
    """Persist a copied grant into the sidecar vault.

    *auth* is the writer's declared credential source; it is recorded on the
    entry so refresh policy is read from the declaration rather than inferred
    from the provider name. The entry is merged into, not replaced: fields this
    caller does not set (status written by the refresh path, plan claims, a
    token endpoint recorded at import time) survive.

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
        if imported_from or "imported_from" not in entry:
            entry["imported_from"] = imported_from
        entry.pop("refresh_in_flight", None)
        providers[provider_name] = entry
        _atomic_write(vault, data)


def get_status(provider_name: str = "xai", *, path: Path | None = None) -> dict[str, Any]:
    vault = path or default_vault_path()
    entry = _load(vault).get("providers", {}).get(provider_name)
    if not isinstance(entry, dict):
        return {"logged_in": False, "path": str(vault)}
    tokens = entry.get("tokens") or {}
    return {
        "logged_in": bool(str(tokens.get("access_token", "")).strip() and str(tokens.get("refresh_token", "")).strip()),
        "path": str(vault),
        "imported_from": entry.get("imported_from") or "",
        "expires_at": (tokens.get("expires_at") if isinstance(tokens, dict) else None),
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


def resolve_bearer(provider: Provider, *, path: Path | None = None) -> str:
    """Return a live Bearer secret for *provider*.

    Blocking: it holds the cross-process vault lock and may refresh the
    credential over the network. Async callers must go through
    ``provider_utils.resolve_bearer_async`` so that a refresh never runs on the
    event loop (KTD1).
    """
    source = auth_source(provider.auth)
    if source is None or not source.vault_backed:
        if provider.api_key:
            return provider.api_key
        raise AuthError(f"Provider '{provider.name}' has no api_key.")

    vault = path or default_vault_path()
    with _vault_lock(vault):
        data = _load(vault)
        entry = data.get("providers", {}).get(provider.name)
        if not isinstance(entry, dict):
            if provider.api_key:
                return provider.api_key
            raise AuthError(
                f"No subscription grant for '{provider.name}' in the vault. "
                f"Run: otel-agent auth login"
            )
        marker = entry.get("refresh_in_flight")
        if marker:
            raise AuthError(
                f"An interrupted refresh left '{provider.name}' in an ambiguous state"
                f"{_marker_detail(marker)}: its refresh token may already have been "
                f"consumed, so it is not presented again automatically. "
                f"The credential must be re-adopted."
            )
        if _needs_refresh(entry):
            # Validate where the token may go *before* recording any intent: a
            # credential that cannot be refreshed is not an ambiguous one.
            target = _refresh_target(entry)
            entry = _begin_refresh(entry)
            data["providers"][provider.name] = entry
            _atomic_write(vault, data)
            payload = _post_refresh(target)
            entry = _finish_refresh(entry, payload)
            data["providers"][provider.name] = entry
            _atomic_write(vault, data)
        raw_tokens = entry.get("tokens")
        tokens: dict[str, Any] = raw_tokens if isinstance(raw_tokens, dict) else {}
        access = str(tokens.get("access_token", "") or "").strip()
        if not access:
            raise AuthError(f"Subscription grant for '{provider.name}' has no access_token.")
        return access


def extract_hermes_xai_grant(store: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Pull usable xAI tokens from a Hermes auth.json object."""
    providers = store.get("providers") if isinstance(store, dict) else None
    state = providers.get("xai-oauth") if isinstance(providers, dict) else None
    tokens = state.get("tokens") if isinstance(state, dict) else None
    if isinstance(tokens, dict) and str(tokens.get("access_token", "")).strip() and str(tokens.get("refresh_token", "")).strip():
        raw_disc = state.get("discovery") if isinstance(state, dict) else None
        discovery: dict[str, Any] = raw_disc if isinstance(raw_disc, dict) else {}
        return tokens, discovery
    pool = store.get("credential_pool") if isinstance(store, dict) else None
    entries = pool.get("xai-oauth") if isinstance(pool, dict) else None
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            access = str(entry.get("access_token", "") or "").strip()
            refresh = str(entry.get("refresh_token", "") or "").strip()
            if access and refresh:
                return (
                    {"access_token": access, "refresh_token": refresh, "token_type": entry.get("token_type") or "Bearer"},
                    {},
                )
    return None

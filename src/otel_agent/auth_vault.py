"""Sidecar OAuth vault for SuperGrok / xAI subscription tokens."""
from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from otel_agent.config import AUTH_XAI_OAUTH, Provider

DEFAULT_VAULT_PATH = Path.home() / ".otel-agent" / "auth.json"
XAI_OAUTH_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_OAUTH_DISCOVERY_URL = "https://auth.x.ai/.well-known/openid-configuration"
XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 3600
DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"

_lock = threading.Lock()


class AuthError(Exception):
    """Raised when a SuperGrok grant is missing or cannot be refreshed."""


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
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def save_grant(
    provider_name: str,
    tokens: dict[str, Any],
    *,
    discovery: dict[str, Any] | None = None,
    imported_from: str = "",
    path: Path | None = None,
) -> None:
    """Persist a copied grant into the sidecar vault."""
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
    with _lock:
        data = _load(vault)
        data["providers"][provider_name] = {
            "auth": AUTH_XAI_OAUTH,
            "tokens": {
                "access_token": access,
                "refresh_token": refresh,
                "token_type": str(tokens.get("token_type") or "Bearer"),
                "expires_at": expires_at,
            },
            "discovery": discovery or {},
            "imported_from": imported_from,
        }
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


def _needs_refresh(tokens: dict[str, Any]) -> bool:
    access = str(tokens.get("access_token", "") or "").strip()
    if not access:
        return True
    expires_at = tokens.get("expires_at")
    if not isinstance(expires_at, (int, float)) or expires_at <= 0:
        exp = _jwt_exp(access)
        expires_at = exp or 0
    if expires_at <= 0:
        return False
    return time.time() >= (expires_at - XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS)


def _token_endpoint(entry: dict[str, Any]) -> str:
    raw_disc = entry.get("discovery")
    discovery: dict[str, Any] = raw_disc if isinstance(raw_disc, dict) else {}
    endpoint = str(discovery.get("token_endpoint", "") or "").strip()
    if endpoint:
        host = (urlparse(endpoint).hostname or "").lower()
        if host.endswith("x.ai"):
            return endpoint
    try:
        resp = httpx.get(XAI_OAUTH_DISCOVERY_URL, headers={"Accept": "application/json"}, timeout=15.0)
        resp.raise_for_status()
        payload = resp.json()
        found = str(payload.get("token_endpoint", "") or "").strip()
        if found:
            return found
    except Exception:
        pass
    return "https://auth.x.ai/oauth2/token"


def _refresh(entry: dict[str, Any]) -> dict[str, Any]:
    raw_tokens = entry.get("tokens")
    tokens: dict[str, Any] = raw_tokens if isinstance(raw_tokens, dict) else {}
    refresh = str(tokens.get("refresh_token", "") or "").strip()
    if not refresh:
        raise AuthError("xAI OAuth grant is missing refresh_token. Re-run: otel-agent auth import-xai")
    endpoint = _token_endpoint(entry)
    resp = httpx.post(
        endpoint,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        data={
            "grant_type": "refresh_token",
            "client_id": XAI_OAUTH_CLIENT_ID,
            "refresh_token": refresh,
        },
        timeout=20.0,
    )
    if resp.status_code != 200:
        raise AuthError(
            f"xAI OAuth refresh failed (HTTP {resp.status_code}). Re-run: otel-agent auth import-xai"
        )
    payload = resp.json()
    access = str(payload.get("access_token", "") or "").strip()
    new_refresh = str(payload.get("refresh_token", "") or "").strip() or refresh
    if not access:
        raise AuthError("xAI OAuth refresh returned no access_token.")
    expires_at = _jwt_exp(access)
    if expires_at is None:
        expires_in = payload.get("expires_in")
        expires_at = int(time.time()) + int(expires_in) if isinstance(expires_in, (int, float)) else 0
    entry = dict(entry)
    entry["tokens"] = {
        "access_token": access,
        "refresh_token": new_refresh,
        "token_type": str(payload.get("token_type") or "Bearer"),
        "expires_at": expires_at,
    }
    return entry


def resolve_bearer(provider: Provider, *, path: Path | None = None) -> str:
    """Return a live Bearer secret for *provider*."""
    if provider.auth != AUTH_XAI_OAUTH:
        if provider.api_key:
            return provider.api_key
        raise AuthError(f"Provider '{provider.name}' has no api_key.")

    vault = path or default_vault_path()
    with _lock:
        data = _load(vault)
        entry = data.get("providers", {}).get(provider.name)
        if not isinstance(entry, dict):
            if provider.api_key:
                return provider.api_key
            raise AuthError(
                f"No xAI OAuth grant for '{provider.name}'. Run: otel-agent auth import-xai"
            )
        raw_tokens = entry.get("tokens")
        tokens: dict[str, Any] = raw_tokens if isinstance(raw_tokens, dict) else {}
        if _needs_refresh(tokens):
            entry = _refresh(entry)
            data["providers"][provider.name] = entry
            _atomic_write(vault, data)
            refreshed = entry.get("tokens")
            tokens = refreshed if isinstance(refreshed, dict) else {}
        access = str(tokens.get("access_token", "") or "").strip()
        if not access:
            raise AuthError(f"xAI OAuth grant for '{provider.name}' has no access_token.")
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

"""Tests for SuperGrok sidecar vault and entitlement rewrite."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from otel_agent.auth_vault import (
    AuthError,
    extract_hermes_xai_grant,
    resolve_bearer,
    save_grant,
)
from otel_agent.config import Provider
from otel_agent.xai_errors import HINT, rewrite_xai_error


def _oauth_provider() -> Provider:
    return Provider(name="xai", base_url="https://api.x.ai/v1", api_key="", auth="xai-oauth")


def test_save_and_resolve_without_refresh(tmp_path, monkeypatch):
    vault = tmp_path / "auth.json"
    hermes = tmp_path / "hermes-auth.json"
    hermes.write_text("{}")
    save_grant(
        "xai",
        {"access_token": "tok-live", "refresh_token": "ref-1", "expires_in": 21600},
        path=vault,
        imported_from="hermes",
    )
    assert vault.stat().st_mode & 0o777 == 0o600
    data = json.loads(vault.read_text())
    assert data["providers"]["xai"]["imported_from"] == "hermes"
    monkeypatch.setattr("otel_agent.auth_vault._needs_refresh", lambda tokens: False)
    assert resolve_bearer(_oauth_provider(), path=vault) == "tok-live"
    assert hermes.read_text() == "{}"


def test_refresh_writes_vault_not_hermes(tmp_path, monkeypatch):
    vault = tmp_path / "auth.json"
    hermes = Path.home() / ".hermes" / "auth.json"
    before = hermes.read_bytes() if hermes.exists() else None
    save_grant(
        "xai",
        {"access_token": "tok-old", "refresh_token": "ref-old", "expires_in": 1},
        path=vault,
    )

    class _Resp:
        status_code = 200

        def json(self):
            return {"access_token": "tok-new", "refresh_token": "ref-new", "expires_in": 21600}

    monkeypatch.setattr("otel_agent.auth_vault._needs_refresh", lambda tokens: True)
    monkeypatch.setattr("otel_agent.auth_vault.httpx.post", lambda *a, **k: _Resp())
    assert resolve_bearer(_oauth_provider(), path=vault) == "tok-new"
    stored = json.loads(vault.read_text())
    assert stored["providers"]["xai"]["tokens"]["refresh_token"] == "ref-new"
    if before is not None:
        assert hermes.read_bytes() == before


def test_extract_hermes_provider_block():
    store = {
        "providers": {
            "xai-oauth": {
                "tokens": {"access_token": "a", "refresh_token": "r"},
                "discovery": {"token_endpoint": "https://auth.x.ai/oauth2/token"},
            }
        }
    }
    grant = extract_hermes_xai_grant(store)
    assert grant is not None
    tokens, discovery = grant
    assert tokens["access_token"] == "a"
    assert discovery["token_endpoint"].endswith("/token")


def test_extract_hermes_pool_fallback():
    store = {
        "credential_pool": {
            "xai-oauth": [{"access_token": "pa", "refresh_token": "pr"}],
        }
    }
    grant = extract_hermes_xai_grant(store)
    assert grant is not None
    assert grant[0]["access_token"] == "pa"


def test_missing_grant_raises(tmp_path):
    vault = tmp_path / "empty.json"
    with pytest.raises(AuthError, match="import-xai"):
        resolve_bearer(_oauth_provider(), path=vault)


def test_rewrite_entitlement_403():
    body = {
        "code": "The caller does not have permission to execute the specified operation",
        "error": "You do not have an active Grok subscription.",
    }
    out = rewrite_xai_error(403, body)
    assert HINT in out["error"]
    assert rewrite_xai_error(401, body)["error"] == body["error"]

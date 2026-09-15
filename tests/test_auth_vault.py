"""Tests for SuperGrok sidecar vault and entitlement rewrite."""
from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

import pytest

from otel_agent.auth_vault import (
    AuthError,
    adopt_grant,
    extract_grant,
    get_status,
    plan_type_from_access_token,
    read_owner_last_refresh,
    resolve_bearer,
    save_grant,
    token_endpoint_from_claims,
)
from otel_agent.commands.auth_cmd import GRANT_SOURCES, grant_sources, handle_auth
from otel_agent.config import Config, Provider
from otel_agent.xai_errors import HINT, is_xai_provider, rewrite_xai_error

XAI_TOKEN_ENDPOINT = "https://auth.x.ai/oauth2/token"


def _oauth_provider() -> Provider:
    return Provider(name="xai", base_url="https://api.x.ai/v1", api_key="", auth="xai-oauth")


def _codex_provider() -> Provider:
    return Provider(
        name="codex",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="",
        auth="codex-oauth",
    )


def test_save_and_resolve_without_refresh(tmp_path, monkeypatch):
    vault = tmp_path / "auth.json"
    hermes = tmp_path / "hermes-auth.json"
    hermes.write_text("{}")
    save_grant(
        "xai",
        {"access_token": "tok-live", "refresh_token": "ref-1", "expires_in": 21600},
        auth="xai-oauth",
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
        auth="xai-oauth",
        discovery={"token_endpoint": XAI_TOKEN_ENDPOINT},
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


def test_extract_grant_from_the_providers_shape():
    store = {
        "providers": {
            "xai-oauth": {
                "tokens": {"access_token": "a", "refresh_token": "r"},
                "discovery": {"token_endpoint": "https://auth.x.ai/oauth2/token"},
            }
        }
    }
    grant = extract_grant(store, grant_sources("xai")[0])
    assert grant is not None
    assert grant.tokens["access_token"] == "a"
    assert grant.discovery["token_endpoint"].endswith("/token")


def test_extract_grant_falls_back_to_the_pool_shape():
    store = {
        "credential_pool": {
            "xai-oauth": [{"access_token": "pa", "refresh_token": "pr"}],
        }
    }
    grant = extract_grant(store, grant_sources("xai")[0])
    assert grant is not None
    assert grant.tokens["access_token"] == "pa"


def test_import_xai_verb_goes_through_the_same_declaration_table(tmp_path, monkeypatch):
    """`import-xai` is a declaration lookup too, not a second code path (D2)."""
    store_path = tmp_path / "hermes.json"
    _write_store(store_path, {
        "providers": {
            "xai-oauth": {
                "tokens": {"access_token": "tok-xai", "refresh_token": "ref-xai"},
                "discovery": {"token_endpoint": XAI_TOKEN_ENDPOINT},
            }
        }
    })
    vault = tmp_path / "auth.json"
    config = tmp_path / "config.yaml"
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(vault))
    monkeypatch.setattr(
        "otel_agent.commands.auth_cmd.GRANT_SOURCES",
        tuple(
            replace(row, path=store_path) if row.provider == "xai" else row
            for row in GRANT_SOURCES
        ),
    )

    handle_auth(Namespace(auth_action="import-xai", config=str(config)))

    entry = json.loads(vault.read_text())["providers"]["xai"]
    assert entry["imported_from"] == "hermes"
    assert entry["tokens"]["access_token"] == "tok-xai"
    assert entry["discovery"]["token_endpoint"] == XAI_TOKEN_ENDPOINT
    provider = Config(config).get_provider("xai")
    assert provider is not None
    assert provider.auth == "xai-oauth"


def test_missing_grant_raises(tmp_path):
    vault = tmp_path / "empty.json"
    with pytest.raises(AuthError, match="auth login"):
        resolve_bearer(_oauth_provider(), path=vault)


def test_save_grant_records_declared_auth_and_merges(tmp_path):
    vault = tmp_path / "auth.json"
    vault.write_text(json.dumps({
        "providers": {
            "codex": {
                "auth": "codex-oauth",
                "tokens": {"access_token": "tok-old", "refresh_token": "ref-old", "expires_at": 1},
                "discovery": {"token_endpoint": "https://auth.openai.com/oauth/token"},
                "plan_type": "plus",
                "last_refresh": "2026-09-15T00:00:00Z",
            }
        }
    }))
    save_grant(
        "codex",
        {"access_token": "tok-new", "refresh_token": "ref-new", "expires_in": 21600},
        auth="codex-oauth",
        path=vault,
    )
    entry = json.loads(vault.read_text())["providers"]["codex"]
    assert entry["auth"] == "codex-oauth"
    assert entry["tokens"]["access_token"] == "tok-new"
    # Fields this writer did not set stay put: the plan claim and the recorded
    # token endpoint both live on this entry and outlive a re-login.
    assert entry["plan_type"] == "plus"
    assert entry["last_refresh"] == "2026-09-15T00:00:00Z"
    assert entry["discovery"]["token_endpoint"] == "https://auth.openai.com/oauth/token"


def test_non_xai_subscription_provider_resolves_bearer(tmp_path, monkeypatch):
    vault = tmp_path / "auth.json"
    save_grant(
        "codex",
        {"access_token": "tok-codex", "refresh_token": "ref-codex", "expires_in": 21600},
        auth="codex-oauth",
        path=vault,
    )
    monkeypatch.setattr("otel_agent.auth_vault._needs_refresh", lambda tokens: False)
    assert resolve_bearer(_codex_provider(), path=vault) == "tok-codex"


def test_undeclared_auth_mode_never_reads_the_vault(tmp_path):
    vault = tmp_path / "auth.json"
    vault.write_text(json.dumps({"providers": {"xai": {"tokens": {"access_token": "tok"}}}}))
    provider = Provider(name="xai", base_url="https://api.x.ai/v1", api_key="key", auth="mystery")
    assert resolve_bearer(provider, path=vault) == "key"


def test_rewrite_entitlement_403():
    body = {
        "code": "The caller does not have permission to execute the specified operation",
        "error": "You do not have an active Grok subscription.",
    }
    out = rewrite_xai_error(403, body)
    assert HINT in out["error"]
    assert rewrite_xai_error(401, body)["error"] == body["error"]


def test_error_rewrite_follows_the_declaration():
    assert is_xai_provider(_oauth_provider())
    # A declared subscription source without the hint is not rewritten.
    assert not is_xai_provider(_codex_provider())
    # No declaration: the api.x.ai host is still recognised.
    assert is_xai_provider(Provider(name="grok", base_url="https://api.x.ai/v1", api_key="k"))


# ------------------------------------------------------------------
# Refresh safety (R4/R5/R6)
# ------------------------------------------------------------------
#
# Every test here reaches the refresh path, so both the token endpoint and the
# POST itself are stubbed: a test must never let a refresh token leave the
# machine, and the xAI discovery document must never be fetched for real.


class _ProcessDied(BaseException):
    """Stands in for the process dying while a refresh is in flight."""


class _RefreshResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _refresh_payload(**overrides) -> dict:
    payload = {"access_token": "tok-new", "refresh_token": "ref-new", "expires_in": 21600}
    payload.update(overrides)
    return payload


def _stub_post(monkeypatch, payload: dict, calls: list) -> None:
    """Stub the token exchange, recording every URL presented a refresh token."""

    def _post(url, *args, **kwargs):
        calls.append(url)
        return _RefreshResponse(payload)

    monkeypatch.setattr("otel_agent.auth_vault.httpx.post", _post)


def _stub_discovery_as_a_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "otel_agent.auth_vault.httpx.get",
        lambda *args, **kwargs: pytest.fail(
            "refresh re-ran endpoint discovery instead of refusing (KTD4)"
        ),
    )


def _seed_vault(vault: Path, entry: dict) -> None:
    vault.write_text(json.dumps({"providers": {"xai": entry}}))


def test_concurrent_callers_of_one_credential_refresh_once(tmp_path, monkeypatch):
    """R5: two callers racing for the same credential reuse one refresh."""
    vault = tmp_path / "auth.json"
    save_grant(
        "xai",
        {"access_token": "tok-old", "refresh_token": "ref-old", "expires_in": 1},
        auth="xai-oauth",
        discovery={"token_endpoint": XAI_TOKEN_ENDPOINT},
        path=vault,
    )
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)
    _stub_discovery_as_a_failure(monkeypatch)

    results: list[str] = []
    start = threading.Barrier(2)

    def _resolve() -> None:
        start.wait()
        results.append(resolve_bearer(_oauth_provider(), path=vault))

    threads = [threading.Thread(target=_resolve) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert posts == [XAI_TOKEN_ENDPOINT]
    assert results == ["tok-new", "tok-new"]
    # The committed pair is the one both callers saw, and the one on disk.
    stored = json.loads(vault.read_text())["providers"]["xai"]
    assert stored["tokens"]["refresh_token"] == "ref-new"


def test_interrupted_refresh_is_recorded_and_needs_re_adoption(tmp_path, monkeypatch):
    """Covers AE3: the process dies after the refresh was issued, before the
    new pair is stored. The intent must survive the crash, and the restarted
    process must not spend the possibly-consumed refresh token again."""
    vault = tmp_path / "auth.json"
    save_grant(
        "xai",
        {"access_token": "tok-old", "refresh_token": "ref-old", "expires_in": 1},
        auth="xai-oauth",
        discovery={"token_endpoint": XAI_TOKEN_ENDPOINT},
        path=vault,
    )
    monkeypatch.setattr("otel_agent.auth_vault._needs_refresh", lambda entry: True)

    def _post_and_die(*args, **kwargs):
        raise _ProcessDied()

    monkeypatch.setattr("otel_agent.auth_vault.httpx.post", _post_and_die)
    with pytest.raises(_ProcessDied):
        resolve_bearer(_oauth_provider(), path=vault)

    # The intent is on disk, so "a refresh may have consumed the token" is
    # distinguishable from "no refresh ever ran".
    entry = json.loads(vault.read_text())["providers"]["xai"]
    assert entry.get("refresh_in_flight"), "no in-flight marker survived the crash"
    assert entry.get("generation") == 1
    # ... and the disk holds the complete pre-refresh pair, not half of a new one.
    assert entry["tokens"]["access_token"] == "tok-old"
    assert entry["tokens"]["refresh_token"] == "ref-old"

    # Restart: no automatic retry of the possibly-consumed refresh token.
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)
    with pytest.raises(AuthError, match="re-adopt"):
        resolve_bearer(_oauth_provider(), path=vault)
    assert posts == []

    # Re-adopting the credential is the remedy, and it clears the marker.
    save_grant(
        "xai",
        {"access_token": "tok-fresh", "refresh_token": "ref-fresh", "expires_in": 21600},
        auth="xai-oauth",
        discovery={"token_endpoint": XAI_TOKEN_ENDPOINT},
        path=vault,
    )
    monkeypatch.setattr("otel_agent.auth_vault._needs_refresh", lambda entry: False)
    assert resolve_bearer(_oauth_provider(), path=vault) == "tok-fresh"


def test_interrupted_marker_is_not_retried_automatically(tmp_path, monkeypatch):
    """R6: a credential left mid-refresh by an earlier process is reported as
    needing re-adoption, not silently refreshed."""
    vault = tmp_path / "auth.json"
    _seed_vault(vault, {
        "auth": "xai-oauth",
        "tokens": {"access_token": "tok-old", "refresh_token": "ref-old", "expires_at": int(time.time()) - 10},
        "discovery": {"token_endpoint": XAI_TOKEN_ENDPOINT},
        "generation": 3,
        "refresh_in_flight": {"generation": 3, "started_at": time.time() - 5},
    })
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)
    _stub_discovery_as_a_failure(monkeypatch)

    with pytest.raises(AuthError, match="re-adopt"):
        resolve_bearer(_oauth_provider(), path=vault)
    assert posts == []


def test_recorded_endpoint_must_match_the_declaration(tmp_path, monkeypatch):
    """KTD4: the endpoint has to be exactly the declared one. A host-suffix
    check accepted `evilx.ai`, which ends with `x.ai`."""
    vault = tmp_path / "auth.json"
    _seed_vault(vault, {
        "auth": "xai-oauth",
        "tokens": {"access_token": "tok-old", "refresh_token": "ref-old", "expires_at": int(time.time()) - 10},
        "discovery": {"token_endpoint": "https://evilx.ai/oauth2/token"},
    })
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)
    _stub_discovery_as_a_failure(monkeypatch)

    with pytest.raises(AuthError, match="token endpoint"):
        resolve_bearer(_oauth_provider(), path=vault)
    assert posts == []


def test_missing_endpoint_refuses_refresh_without_discovery(tmp_path, monkeypatch):
    """R4: no recorded endpoint means no refresh — never the vendor default."""
    vault = tmp_path / "auth.json"
    _seed_vault(vault, {
        "auth": "xai-oauth",
        "tokens": {"access_token": "tok-old", "refresh_token": "ref-old", "expires_at": int(time.time()) - 10},
        "discovery": {},
    })
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)
    _stub_discovery_as_a_failure(monkeypatch)

    with pytest.raises(AuthError, match="token endpoint"):
        resolve_bearer(_oauth_provider(), path=vault)
    assert posts == []


def test_refresh_without_a_new_refresh_token_is_an_error(tmp_path, monkeypatch):
    """A rotated grant whose response omits the new refresh token must not
    silently keep the one the exchange just consumed."""
    vault = tmp_path / "auth.json"
    vault.write_text(json.dumps({
        "providers": {
            "xai": {
                "auth": "xai-oauth",
                "tokens": {"access_token": "tok-old", "refresh_token": "ref-old", "expires_at": int(time.time()) - 10},
                "discovery": {"token_endpoint": XAI_TOKEN_ENDPOINT},
            }
        }
    }))
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(refresh_token=None), posts)

    with pytest.raises(AuthError, match="refresh_token"):
        resolve_bearer(_oauth_provider(), path=vault)

    assert posts == [XAI_TOKEN_ENDPOINT]
    stored = json.loads(vault.read_text())["providers"]["xai"]
    assert stored["tokens"]["refresh_token"] == "ref-old"
    assert stored["tokens"]["access_token"] == "tok-old"


def test_opaque_access_token_is_not_treated_as_never_expiring(tmp_path, monkeypatch):
    """An access token whose lifetime cannot be read has no proven expiry, so
    it is refreshed rather than served forever."""
    vault = tmp_path / "auth.json"
    vault.write_text(json.dumps({
        "providers": {
            "xai": {
                "auth": "xai-oauth",
                "tokens": {"access_token": "opaque-token", "refresh_token": "ref-old", "expires_at": 0},
                "discovery": {"token_endpoint": XAI_TOKEN_ENDPOINT},
            }
        }
    }))
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)

    assert resolve_bearer(_oauth_provider(), path=vault) == "tok-new"
    assert posts == [XAI_TOKEN_ENDPOINT]


def test_refresh_cadence_follows_the_provider_declaration(tmp_path, monkeypatch):
    """A token with a lifetime shorter than xAI's 3600s skew must not be
    refreshed on every request: each refresh spends a one-time refresh token."""
    vault = tmp_path / "auth.json"
    vault.write_text(json.dumps({
        "providers": {
            "codex": {
                "auth": "codex-oauth",
                "tokens": {
                    "access_token": "tok-codex",
                    "refresh_token": "ref-codex",
                    "expires_at": int(time.time()) + 600,
                },
                "discovery": {"token_endpoint": "https://auth.openai.com/oauth/token"},
            }
        }
    }))
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)
    _stub_discovery_as_a_failure(monkeypatch)

    assert resolve_bearer(_codex_provider(), path=vault) == "tok-codex"
    assert posts == []


def test_vault_lock_excludes_and_times_out(tmp_path):
    """KTD2: the lock is a cross-process one (flock), it is released on exit,
    and a caller that cannot get it gives up instead of hanging forever."""
    from otel_agent.auth_vault import _vault_lock

    vault = tmp_path / "auth.json"
    with _vault_lock(vault, timeout=1.0):
        # A second holder — a second open file description, exactly as a second
        # process would have — must not be able to enter.
        with pytest.raises(AuthError, match="vault lock"):
            with _vault_lock(vault, timeout=0.1):
                pass
    # Released on exit, so the next writer gets in.
    with _vault_lock(vault, timeout=0.5):
        pass
    # The lock lives on a sibling the atomic write never replaces, so both
    # writers always contend on the same inode.
    assert (tmp_path / "auth.json.lock").exists()
    assert not vault.exists()


def test_save_grant_waits_for_the_same_lock(tmp_path, monkeypatch):
    """The CLI writers (auth login / import-xai) take the daemon's lock."""
    from otel_agent.auth_vault import _vault_lock

    vault = tmp_path / "auth.json"
    monkeypatch.setattr("otel_agent.auth_vault._LOCK_TIMEOUT_SECONDS", 0.05)
    errors: list = []

    def _save() -> None:
        try:
            save_grant(
                "xai",
                {"access_token": "tok", "refresh_token": "ref", "expires_in": 60},
                auth="xai-oauth",
                discovery={"token_endpoint": XAI_TOKEN_ENDPOINT},
                path=vault,
            )
        except Exception as exc:  # noqa: BLE001 - recorded for the assertion
            errors.append(exc)

    with _vault_lock(vault, timeout=5.0):
        thread = threading.Thread(target=_save)
        thread.start()
        thread.join()

    assert len(errors) == 1 and isinstance(errors[0], AuthError)
    assert not vault.exists()
    # Once the holder releases, the same write goes through.
    save_grant(
        "xai",
        {"access_token": "tok", "refresh_token": "ref", "expires_in": 60},
        auth="xai-oauth",
        discovery={"token_endpoint": XAI_TOKEN_ENDPOINT},
        path=vault,
    )
    assert json.loads(vault.read_text())["providers"]["xai"]["tokens"]["access_token"] == "tok"


def test_refresh_leaves_the_owner_cli_file_untouched(tmp_path, monkeypatch):
    """A refresh writes the vault and nothing else — the file the grant came
    from is never a writer's target."""
    home = tmp_path / "home"
    hermes = home / ".hermes" / "auth.json"
    hermes.parent.mkdir(parents=True)
    hermes.write_text(json.dumps({
        "providers": {"xai-oauth": {"tokens": {"access_token": "tok-old", "refresh_token": "ref-old"}}}
    }))
    before = hermes.read_bytes()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))

    vault = tmp_path / "auth.json"
    save_grant(
        "xai",
        {"access_token": "tok-old", "refresh_token": "ref-old", "expires_in": 1},
        auth="xai-oauth",
        discovery={"token_endpoint": XAI_TOKEN_ENDPOINT},
        path=vault,
    )
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)

    assert resolve_bearer(_oauth_provider(), path=vault) == "tok-new"
    assert posts == [XAI_TOKEN_ENDPOINT]
    assert hermes.read_bytes() == before
    assert json.loads(vault.read_text())["providers"]["xai"]["tokens"]["access_token"] == "tok-new"


# ------------------------------------------------------------------
# Adopting a sibling CLI's Codex grant (R3 / F1)
# ------------------------------------------------------------------
#
# The shapes below are those of the real `~/.hermes/auth.json` on this machine,
# reproduced as fixtures: `providers["openai-codex"]` carries only
# `tokens`/`last_refresh`/`auth_mode`, while `credential_pool["openai-codex"][0]`
# carries `base_url`/`source`/`label` and the pair flat. Nothing here reads the
# real file, and no test ever lets a refresh token leave the machine.

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
CODEX_TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
CODEX_CLIENT_ID = "app_codex_test"


def _jwt(claims: dict) -> str:
    """A structurally valid JWT whose payload is *claims*."""

    def _segment(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{_segment({'alg': 'RS256', 'typ': 'JWT'})}.{_segment(claims)}.sig"


def _codex_access_token(*, iss: str = "https://auth.openai.com", client_id: str = CODEX_CLIENT_ID) -> str:
    return _jwt({"iss": iss, "client_id": client_id, "exp": int(time.time()) + 86400})


def _codex_store(*, access: str | None = None, providers: bool = True, pool: bool = True) -> dict:
    access = access if access is not None else _codex_access_token()
    store: dict = {}
    if providers:
        store["providers"] = {
            "openai-codex": {
                "tokens": {"access_token": access, "refresh_token": "ref-owner"},
                "last_refresh": "2026-09-15T05:31:37.965237Z",
                "auth_mode": "chatgpt",
            }
        }
    if pool:
        store["credential_pool"] = {
            "openai-codex": [
                {
                    "id": "073100",
                    "label": "device_code",
                    "auth_type": "oauth",
                    "priority": 0,
                    "source": "device_code",
                    "access_token": access,
                    "refresh_token": "ref-owner",
                    "base_url": CODEX_BASE_URL,
                    "last_refresh": "2026-09-15T05:31:37.965237Z",
                    "request_count": 0,
                }
            ]
        }
    return store


def _codex_source(store_path: Path):
    """The real declared source row, pointed at a fixture store instead."""
    return replace(grant_sources("codex")[0], path=store_path)


def _write_store(store_path: Path, store: dict) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")


def _adopted_entry(vault: Path) -> dict:
    return json.loads(vault.read_text())["providers"]["codex"]


def test_adopt_codex_grant_from_the_providers_shape(tmp_path, monkeypatch):
    """A store that only has `providers[...]` still yields an adoptable grant."""
    store_path = tmp_path / "hermes.json"
    access = _codex_access_token()
    _write_store(store_path, _codex_store(access=access, pool=False))
    vault = tmp_path / "auth.json"
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)

    adoption = adopt_grant(_codex_source(store_path), path=vault)

    entry = _adopted_entry(vault)
    assert entry["auth"] == "codex-oauth"
    assert entry["imported_from"] == "hermes"
    assert entry["tokens"]["refresh_token"] == "ref-new"
    # base_url is nowhere in this shape, so the declaration supplies it.
    assert adoption.base_url == CODEX_BASE_URL


def test_adopt_codex_grant_from_the_credential_pool_shape(tmp_path, monkeypatch):
    """`base_url` comes off the pool entry, not off `providers[...]`."""
    store_path = tmp_path / "hermes.json"
    store = _codex_store()
    # A decoy on the nodes the pool pointer must win over. The real
    # `providers["openai-codex"]` carries no base_url at all; the decoy is here
    # so that reordering the declared pointers fails this test.
    store["providers"]["openai-codex"]["base_url"] = "https://decoy.invalid/v1"
    _write_store(store_path, store)
    vault = tmp_path / "auth.json"
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)

    adoption = adopt_grant(_codex_source(store_path), path=vault)

    assert adoption.base_url == CODEX_BASE_URL
    assert _adopted_entry(vault)["tokens"]["refresh_token"] == "ref-new"


def test_adopt_records_the_endpoint_and_client_id_from_the_grants_own_claims(tmp_path, monkeypatch):
    """R4/KTD4: the store names no token endpoint, so the grant's own `iss` and
    `client_id` claim are what a later refresh will present — and a refresh with
    no recorded endpoint is refused, so adoption without this step is broken."""
    store_path = tmp_path / "hermes.json"
    _write_store(store_path, _codex_store())
    vault = tmp_path / "auth.json"
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)

    adopt_grant(_codex_source(store_path), path=vault)

    entry = _adopted_entry(vault)
    assert entry["discovery"]["token_endpoint"] == CODEX_TOKEN_ENDPOINT
    assert entry["client_id"] == CODEX_CLIENT_ID
    # ... and that recorded endpoint is exactly where the refresh was sent.
    assert posts == [CODEX_TOKEN_ENDPOINT]


def test_token_endpoint_follows_the_grants_own_issuer():
    assert token_endpoint_from_claims({"iss": "https://auth.openai.com"}) == CODEX_TOKEN_ENDPOINT
    assert token_endpoint_from_claims({"iss": "https://auth.openai.com/"}) == CODEX_TOKEN_ENDPOINT
    # No issuer, or one that is not an https host, yields nothing: the
    # derivation follows the credential rather than a vendor default (KTD4).
    assert token_endpoint_from_claims({}) == ""
    assert token_endpoint_from_claims({"iss": "http://auth.openai.com"}) == ""
    assert token_endpoint_from_claims({"iss": "auth.openai.com"}) == ""


def test_adopt_refuses_a_grant_that_cannot_yield_a_token_endpoint(tmp_path, monkeypatch):
    """Better a refusal at adoption than a hard-failing refresh afterwards."""
    store_path = tmp_path / "hermes.json"
    _write_store(store_path, _codex_store(access=_jwt({"exp": int(time.time()) + 86400})))
    vault = tmp_path / "auth.json"
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)

    with pytest.raises(AuthError, match="token endpoint"):
        adopt_grant(_codex_source(store_path), path=vault)

    assert posts == []
    assert not vault.exists(), "a refused adoption must not leave a half-written vault"


def test_adopt_without_a_sibling_store_says_so(tmp_path):
    vault = tmp_path / "auth.json"
    with pytest.raises(AuthError, match="does not exist"):
        adopt_grant(_codex_source(tmp_path / "nope.json"), path=vault)
    assert not vault.exists()


def test_adopt_leaves_the_owner_file_byte_identical(tmp_path, monkeypatch):
    """R3: the owner CLI's file is read, never written."""
    store_path = tmp_path / "hermes.json"
    _write_store(store_path, _codex_store())
    before = store_path.read_bytes()
    digest = hashlib.sha256(before).hexdigest()
    vault = tmp_path / "auth.json"
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)

    adopt_grant(_codex_source(store_path), path=vault)

    assert store_path.read_bytes() == before
    assert hashlib.sha256(store_path.read_bytes()).hexdigest() == digest


def test_adopt_takes_over_the_chain_with_one_immediate_refresh(tmp_path, monkeypatch):
    """F1: adoption refreshes at once, so the gateway — not the sibling — is the
    writer that spends the old refresh token. The adopted access token is a
    valid, unexpired JWT, so an adoption that merely waited for expiry would
    post nothing here."""
    store_path = tmp_path / "hermes.json"
    adopted = _codex_access_token()
    _write_store(store_path, _codex_store(access=adopted))
    vault = tmp_path / "auth.json"
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(access_token="tok-handed-over", refresh_token="ref-handed-over"), posts)

    adoption = adopt_grant(_codex_source(store_path), path=vault)

    assert posts == [CODEX_TOKEN_ENDPOINT]
    assert adoption.bearer == "tok-handed-over"
    stored = _adopted_entry(vault)
    assert stored["tokens"]["access_token"] == "tok-handed-over"
    assert stored["tokens"]["refresh_token"] == "ref-handed-over"
    # The pair on disk is the refreshed one, and adoption left no ambiguity.
    assert stored["tokens"]["access_token"] != adopted
    assert stored["tokens"]["refresh_token"] != "ref-owner"
    assert "refresh_in_flight" not in stored
    # The entry adoption left behind is complete enough for the ordinary
    # resolver: it serves the live token and spends no second exchange.
    posts.clear()
    assert resolve_bearer(_codex_provider(), path=vault) == "tok-handed-over"
    assert posts == []


def test_adopt_verb_writes_the_provider_row_and_prints_the_handoff(tmp_path, monkeypatch, capsys):
    """The CLI verb: one declaration lookup, one provider row, one hand-off."""
    store_path = tmp_path / "hermes.json"
    _write_store(store_path, _codex_store())
    before = store_path.read_bytes()
    vault = tmp_path / "auth.json"
    config = tmp_path / "config.yaml"
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(vault))
    monkeypatch.setattr(
        "otel_agent.commands.auth_cmd.GRANT_SOURCES",
        tuple(replace(row, path=store_path) if row.provider == "codex" else row for row in GRANT_SOURCES),
    )
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)

    handle_auth(Namespace(auth_action="import-codex", config=str(config)))

    out = capsys.readouterr().out
    provider = Config(config).get_provider("codex")
    assert provider is not None
    assert provider.auth == "codex-oauth"
    assert provider.base_url == CODEX_BASE_URL
    assert provider.api_key == ""
    assert _adopted_entry(vault)["tokens"]["refresh_token"] == "ref-new"
    assert store_path.read_bytes() == before
    # F1's closing step is part of the output, not an optional extra.
    assert "Hand-off" in out
    assert "gateway" in out


def test_adopt_verb_reports_a_missing_sibling_store(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(tmp_path / "auth.json"))
    monkeypatch.setattr(
        "otel_agent.commands.auth_cmd.GRANT_SOURCES",
        tuple(
            replace(row, path=tmp_path / "nope.json") if row.provider == "codex" else row
            for row in GRANT_SOURCES
        ),
    )
    with pytest.raises(SystemExit):
        handle_auth(Namespace(auth_action="import-codex", config=str(tmp_path / "config.yaml")))
    assert "not signed in" in capsys.readouterr().out


# ------------------------------------------------------------------
# Subscription status and diagnosable credential failures (R11 / R12)
# ------------------------------------------------------------------


def _plan_bearing_token(*, plan: str = "prolite", exp: int | None = None) -> str:
    """An access token shaped like the real one: the tier rides a URL-shaped
    claim rather than a top-level one."""
    return _jwt({
        "iss": "https://auth.openai.com",
        "client_id": CODEX_CLIENT_ID,
        "exp": exp if exp is not None else int(time.time()) + 86400,
        "https://api.openai.com/auth": {
            "chatgpt_plan_type": plan,
            "chatgpt_account_id": "acct-0000",
        },
    })


def _seed_codex_entry(vault: Path, **overrides) -> None:
    entry: dict = {
        "auth": "codex-oauth",
        "tokens": {
            "access_token": _plan_bearing_token(),
            "refresh_token": "ref-codex",
            "expires_at": int(time.time()) + 86400,
        },
        "discovery": {"token_endpoint": CODEX_TOKEN_ENDPOINT},
        "client_id": CODEX_CLIENT_ID,
    }
    entry.update(overrides)
    vault.write_text(json.dumps({"providers": {"codex": entry}}))


class _RejectedResponse:
    """A token endpoint refusing the refresh."""

    status_code = 401

    def json(self) -> dict:
        return {"error": "invalid_grant"}


def test_status_answers_all_four_things_r11_asks_for(tmp_path):
    """可用 / 档位 / 到期时间 / 上次结果, in one call."""
    vault = tmp_path / "auth.json"
    _seed_codex_entry(
        vault,
        plan_type="plus",
        last_refresh="2026-09-15T05:31:37Z",
        last_refresh_result={"at": 1757914297.0, "ok": True, "detail": ""},
    )

    status = get_status("codex", path=vault)

    assert status["available"] is True
    assert status["plan"] == "prolite"
    assert isinstance(status["expires_at"], int) and status["expires_at"] > time.time()
    assert status["last_result"]["ok"] is True
    assert status["last_result"]["at"] == 1757914297.0


def test_status_reflects_a_failed_refresh(tmp_path, monkeypatch):
    """R11: after a refresh fails, the status says so rather than going quiet."""
    vault = tmp_path / "auth.json"
    _seed_codex_entry(vault, tokens={
        "access_token": "tok-old",
        "refresh_token": "ref-old",
        "expires_at": int(time.time()) - 10,
    })
    monkeypatch.setattr("otel_agent.auth_vault._needs_refresh", lambda entry: True)
    monkeypatch.setattr(
        "otel_agent.auth_vault.httpx.post", lambda *a, **k: _RejectedResponse()
    )

    with pytest.raises(AuthError, match="401"):
        resolve_bearer(_codex_provider(), path=vault)

    status = get_status("codex", path=vault)
    assert status["last_result"]["ok"] is False
    assert "401" in status["last_result"]["detail"]


def test_status_reflects_a_refused_refresh(tmp_path, monkeypatch):
    """A refusal before the exchange is a result too: it is what tells the
    operator the credential must be re-adopted rather than retried."""
    vault = tmp_path / "auth.json"
    _seed_codex_entry(vault, discovery={})
    monkeypatch.setattr("otel_agent.auth_vault._needs_refresh", lambda entry: True)
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)
    _stub_discovery_as_a_failure(monkeypatch)

    with pytest.raises(AuthError, match="token endpoint"):
        resolve_bearer(_codex_provider(), path=vault)

    assert posts == []
    status = get_status("codex", path=vault)
    assert status["last_result"]["ok"] is False
    assert "token endpoint" in status["last_result"]["detail"]


def test_a_successful_refresh_becomes_the_last_result(tmp_path, monkeypatch):
    vault = tmp_path / "auth.json"
    _seed_codex_entry(vault, tokens={
        "access_token": "tok-old",
        "refresh_token": "ref-old",
        "expires_at": int(time.time()) - 10,
    })
    monkeypatch.setattr("otel_agent.auth_vault._needs_refresh", lambda entry: True)
    posts: list = []
    _stub_post(monkeypatch, _refresh_payload(), posts)

    assert resolve_bearer(_codex_provider(), path=vault) == "tok-new"

    status = get_status("codex", path=vault)
    assert status["last_result"]["ok"] is True
    assert status["last_refresh"].endswith("Z")


def test_status_marks_a_grant_left_mid_refresh_as_unavailable(tmp_path):
    """The pair is on disk, but the resolver refuses it: the tier of the answer
    R11 asks for must not claim otherwise."""
    vault = tmp_path / "auth.json"
    _seed_codex_entry(vault, refresh_in_flight={"generation": 1, "started_at": time.time()})

    status = get_status("codex", path=vault)

    assert status["logged_in"] is True
    assert status["available"] is False


def test_save_grant_keeps_the_recorded_status_fields(tmp_path):
    """KTD9: a re-login merges, so what the status surface reads survives it."""
    vault = tmp_path / "auth.json"
    _seed_codex_entry(
        vault,
        plan_type="plus",
        last_refresh="2026-09-15T05:31:37Z",
        last_refresh_result={"at": 1757914297.0, "ok": True, "detail": ""},
    )
    save_grant(
        "codex",
        {"access_token": "tok-new", "refresh_token": "ref-new", "expires_in": 21600},
        auth="codex-oauth",
        path=vault,
    )

    entry = json.loads(vault.read_text())["providers"]["codex"]
    assert entry["last_refresh"] == "2026-09-15T05:31:37Z"
    assert entry["last_refresh_result"]["ok"] is True
    assert entry["plan_type"] == "plus"
    # ... and the status surface still reads them.
    status = get_status("codex", path=vault)
    assert status["last_result"]["at"] == 1757914297.0


def test_status_of_an_absent_grant_says_so(tmp_path):
    status = get_status("codex", path=tmp_path / "absent.json")
    assert status["logged_in"] is False
    assert status["available"] is False
    assert status["plan"] == ""
    assert status["last_result"] is None
    assert status["expires_at"] is None


def test_plan_type_is_read_off_the_grants_own_claims():
    assert plan_type_from_access_token(_plan_bearing_token(plan="prolite")) == "prolite"
    assert plan_type_from_access_token(_plan_bearing_token(plan="plus")) == "plus"
    # No tier named means no tier claimed, never a guess.
    assert plan_type_from_access_token(_jwt({"exp": 1})) == ""
    assert plan_type_from_access_token("opaque-token") == ""


def test_credential_errors_name_the_provider_they_are_about(tmp_path, monkeypatch):
    """The app-level handler needs the provider to attach the status (R12)."""
    with pytest.raises(AuthError) as missing:
        resolve_bearer(_codex_provider(), path=tmp_path / "absent.json")
    assert missing.value.provider == "codex"

    vault = tmp_path / "auth.json"
    _seed_codex_entry(vault, tokens={
        "access_token": "tok-old",
        "refresh_token": "ref-old",
        "expires_at": int(time.time()) - 10,
    })
    monkeypatch.setattr("otel_agent.auth_vault._needs_refresh", lambda entry: True)
    monkeypatch.setattr(
        "otel_agent.auth_vault.httpx.post", lambda *a, **k: _RejectedResponse()
    )
    with pytest.raises(AuthError) as failed:
        resolve_bearer(_codex_provider(), path=vault)
    assert failed.value.provider == "codex"


def test_owner_last_refresh_is_read_from_the_owning_store(tmp_path):
    store_path = tmp_path / "hermes.json"
    _write_store(store_path, _codex_store())
    assert read_owner_last_refresh(_codex_source(store_path)) == "2026-09-15T05:31:37.965237Z"


def test_owner_last_refresh_degrades_when_nothing_can_be_read(tmp_path):
    """Most machines have no sibling CLI installed; that is not a doctor error."""
    assert read_owner_last_refresh(_codex_source(tmp_path / "nope.json")) == ""
    junk = tmp_path / "junk.json"
    junk.write_text("not json")
    assert read_owner_last_refresh(_codex_source(junk)) == ""
    _write_store(junk, {"credential_pool": {"openai-codex": [{"refresh_token": "r"}]}})
    assert read_owner_last_refresh(_codex_source(junk)) == ""

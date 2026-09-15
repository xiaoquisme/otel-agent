"""Tests for SuperGrok sidecar vault and entitlement rewrite."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from otel_agent.auth_vault import (
    AuthError,
    extract_hermes_xai_grant,
    resolve_bearer,
    save_grant,
)
from otel_agent.config import Provider
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

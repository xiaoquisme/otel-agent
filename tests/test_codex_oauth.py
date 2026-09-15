"""Tests for the Codex device-code login — an independent chain, sibling CLIs untouched."""
from __future__ import annotations

import json
from argparse import Namespace
from datetime import datetime, timedelta, timezone

import pytest

from otel_agent.auth_vault import AuthError
from otel_agent.codex_oauth import (
    CODEX_DEVICE_AUTH_WINDOW_SECONDS,
    CODEX_OAUTH_CLIENT_ID,
    CODEX_OAUTH_DEVICE_CODE_URL,
    CODEX_OAUTH_DEVICE_TOKEN_URL,
    CODEX_OAUTH_TOKEN_URL,
    CODEX_OAUTH_VERIFICATION_URL,
    exchange_authorization_code,
    poll_device_token,
    request_device_code,
)
from otel_agent.commands.auth_cmd import handle_auth
from otel_agent.config import Config


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


def _device_payload(**overrides) -> dict:
    payload = {"device_auth_id": "dev-1", "user_code": "ABCD-1234", "interval": 1}
    payload.update(overrides)
    return payload


# --- step 1: the usercode request -------------------------------------------


def test_request_device_code_posts_the_public_client_id():
    seen: dict = {}

    class _Client:
        def post(self, url, **kwargs):
            seen["url"] = str(url)
            seen["json"] = kwargs.get("json")
            return _Resp(200, _device_payload())

    device = request_device_code(_Client())  # type: ignore[arg-type]
    assert seen["url"] == CODEX_OAUTH_DEVICE_CODE_URL
    assert seen["json"] == {"client_id": CODEX_OAUTH_CLIENT_ID}
    assert device["device_auth_id"] == "dev-1"
    assert device["user_code"] == "ABCD-1234"


def test_request_device_code_requires_fields():
    class _Client:
        def post(self, url, **kwargs):
            return _Resp(200, {"device_auth_id": "dev-1"})

    with pytest.raises(AuthError, match="missing fields"):
        request_device_code(_Client())  # type: ignore[arg-type]


def test_request_device_code_disabled_reports_the_status_instead_of_hanging():
    class _Client:
        def post(self, url, **kwargs):
            return _Resp(403, text="device authorization is disabled for this workspace")

    with pytest.raises(AuthError) as excinfo:
        request_device_code(_Client())  # type: ignore[arg-type]
    assert "403" in str(excinfo.value)
    assert "disabled" in str(excinfo.value)


def test_request_device_code_coerces_the_string_interval():
    class _Client:
        def post(self, url, **kwargs):
            return _Resp(200, _device_payload(interval="5"))

    assert request_device_code(_Client())["interval"] == 5  # type: ignore[arg-type]


def test_request_device_code_floors_a_zero_or_missing_interval():
    class _Zero:
        def post(self, url, **kwargs):
            return _Resp(200, _device_payload(interval="0"))

    class _Missing:
        def post(self, url, **kwargs):
            payload = _device_payload()
            payload.pop("interval")
            return _Resp(200, payload)

    class _Garbage:
        def post(self, url, **kwargs):
            return _Resp(200, _device_payload(interval="soon"))

    assert request_device_code(_Zero())["interval"] == 1  # type: ignore[arg-type]
    assert request_device_code(_Missing())["interval"] == 1  # type: ignore[arg-type]
    assert request_device_code(_Garbage())["interval"] == 1  # type: ignore[arg-type]


def test_request_device_code_derives_the_window_from_expires_at():
    """The host sends an absolute instant; the window is what is left of it."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=3600)

    class _Client:
        def post(self, url, **kwargs):
            return _Resp(200, _device_payload(expires_at=expires_at.isoformat()))

    window = request_device_code(_Client())["expires_in"]  # type: ignore[arg-type]
    assert 3590 <= window <= 3600


def test_request_device_code_reads_expires_at_in_its_own_offset():
    """``+02:00`` is the same instant as the UTC form, not two hours later."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=600)
    offset = timezone(timedelta(hours=2))
    encoded = expires_at.astimezone(offset).isoformat()

    class _Client:
        def post(self, url, **kwargs):
            return _Resp(200, _device_payload(expires_at=encoded))

    window = request_device_code(_Client())["expires_in"]  # type: ignore[arg-type]
    assert 590 <= window <= 600


def test_request_device_code_falls_back_to_the_constant_without_expires_at():
    class _Absent:
        def post(self, url, **kwargs):
            return _Resp(200, _device_payload())

    class _Null:
        def post(self, url, **kwargs):
            return _Resp(200, _device_payload(expires_at=None))

    class _Empty:
        def post(self, url, **kwargs):
            return _Resp(200, _device_payload(expires_at="  "))

    assert request_device_code(_Absent())["expires_in"] == CODEX_DEVICE_AUTH_WINDOW_SECONDS  # type: ignore[arg-type]
    assert request_device_code(_Null())["expires_in"] == CODEX_DEVICE_AUTH_WINDOW_SECONDS  # type: ignore[arg-type]
    assert request_device_code(_Empty())["expires_in"] == CODEX_DEVICE_AUTH_WINDOW_SECONDS  # type: ignore[arg-type]


def test_request_device_code_falls_back_on_an_unusable_expires_at():
    class _Garbage:
        def post(self, url, **kwargs):
            return _Resp(200, _device_payload(expires_at="next tuesday"))

    class _OutOfRange:
        def post(self, url, **kwargs):
            return _Resp(200, _device_payload(expires_at="2026-13-45T99:99:99+00:00"))

    class _NoOffset:
        # Ambiguous rather than wrong: an offset-less value read in the wrong
        # zone would set the deadline hours out, so it is not trusted.
        def post(self, url, **kwargs):
            return _Resp(200, _device_payload(expires_at="2026-09-15T13:51:24.776245"))

    assert request_device_code(_Garbage())["expires_in"] == CODEX_DEVICE_AUTH_WINDOW_SECONDS  # type: ignore[arg-type]
    assert request_device_code(_OutOfRange())["expires_in"] == CODEX_DEVICE_AUTH_WINDOW_SECONDS  # type: ignore[arg-type]
    assert request_device_code(_NoOffset())["expires_in"] == CODEX_DEVICE_AUTH_WINDOW_SECONDS  # type: ignore[arg-type]


# --- step 3: the poll loop --------------------------------------------------


def test_poll_treats_403_and_404_as_still_pending():
    responses = [
        _Resp(403, text=""),
        _Resp(404, text=""),
        _Resp(200, {"authorization_code": "ac-1", "code_verifier": "cv-1"}),
    ]
    seen: dict = {}

    class _Client:
        def post(self, url, **kwargs):
            seen["url"] = str(url)
            seen["json"] = kwargs.get("json")
            return responses.pop(0)

    sleeps: list[float] = []
    clock = {"t": 0.0}

    challenge = poll_device_token(
        _Client(),  # type: ignore[arg-type]
        token_endpoint=CODEX_OAUTH_DEVICE_TOKEN_URL,
        device_auth_id="dev-1",
        user_code="ABCD-1234",
        expires_in=900,
        poll_interval=2,
        sleep=lambda s: (sleeps.append(s), clock.__setitem__("t", clock["t"] + s)),
        monotonic=lambda: clock["t"],
    )
    assert challenge == {"authorization_code": "ac-1", "code_verifier": "cv-1"}
    assert sleeps == [2, 2]
    assert seen["url"] == CODEX_OAUTH_DEVICE_TOKEN_URL
    assert seen["json"] == {"device_auth_id": "dev-1", "user_code": "ABCD-1234"}


def test_poll_pending_then_success():
    responses = [
        _Resp(400, {"error": "authorization_pending"}),
        _Resp(200, {"authorization_code": "ac-1", "code_verifier": "cv-1"}),
    ]

    class _Client:
        def post(self, url, **kwargs):
            return responses.pop(0)

    sleeps: list[float] = []
    clock = {"t": 0.0}

    challenge = poll_device_token(
        _Client(),  # type: ignore[arg-type]
        token_endpoint=CODEX_OAUTH_DEVICE_TOKEN_URL,
        device_auth_id="dev-1",
        user_code="ABCD-1234",
        expires_in=900,
        poll_interval=3,
        sleep=lambda s: (sleeps.append(s), clock.__setitem__("t", clock["t"] + s)),
        monotonic=lambda: clock["t"],
    )
    assert challenge["authorization_code"] == "ac-1"
    assert sleeps == [3]


def test_poll_slow_down_bumps_interval():
    responses = [
        _Resp(400, {"error": "slow_down"}),
        _Resp(200, {"authorization_code": "ac-1", "code_verifier": "cv-1"}),
    ]

    class _Client:
        def post(self, url, **kwargs):
            return responses.pop(0)

    sleeps: list[float] = []
    clock = {"t": 0.0}
    poll_device_token(
        _Client(),  # type: ignore[arg-type]
        token_endpoint=CODEX_OAUTH_DEVICE_TOKEN_URL,
        device_auth_id="dev-1",
        user_code="ABCD-1234",
        expires_in=900,
        poll_interval=2,
        sleep=lambda s: (sleeps.append(s), clock.__setitem__("t", clock["t"] + s)),
        monotonic=lambda: clock["t"],
    )
    assert sleeps == [3]


def test_poll_denied():
    class _Client:
        def post(self, url, **kwargs):
            return _Resp(400, {"error": "access_denied", "error_description": "nope"})

    with pytest.raises(AuthError, match="nope"):
        poll_device_token(
            _Client(),  # type: ignore[arg-type]
            token_endpoint=CODEX_OAUTH_DEVICE_TOKEN_URL,
            device_auth_id="dev-1",
            user_code="ABCD-1234",
            expires_in=900,
            poll_interval=1,
            sleep=lambda s: None,
            monotonic=lambda: 0.0,
        )


def test_poll_timeout():
    class _Client:
        def post(self, url, **kwargs):
            return _Resp(403, text="")

    clock = {"t": 0.0}

    def sleep(seconds):
        clock["t"] += 100

    with pytest.raises(AuthError, match="Timed out"):
        poll_device_token(
            _Client(),  # type: ignore[arg-type]
            token_endpoint=CODEX_OAUTH_DEVICE_TOKEN_URL,
            device_auth_id="dev-1",
            user_code="ABCD-1234",
            expires_in=900,
            poll_interval=1,
            sleep=sleep,
            monotonic=lambda: clock["t"],
        )


def test_poll_requires_the_code_and_verifier():
    class _Client:
        def post(self, url, **kwargs):
            return _Resp(200, {"authorization_code": "ac-1"})

    with pytest.raises(AuthError, match="code_verifier"):
        poll_device_token(
            _Client(),  # type: ignore[arg-type]
            token_endpoint=CODEX_OAUTH_DEVICE_TOKEN_URL,
            device_auth_id="dev-1",
            user_code="ABCD-1234",
            expires_in=900,
            poll_interval=1,
            sleep=lambda s: None,
            monotonic=lambda: 0.0,
        )


# --- step 4: the authorization-code exchange --------------------------------


def test_exchange_posts_the_authorization_code_grant():
    seen: dict = {}

    class _Client:
        def post(self, url, **kwargs):
            seen["url"] = str(url)
            seen["data"] = kwargs.get("data")
            seen["headers"] = kwargs.get("headers")
            return _Resp(200, {"access_token": "tok", "refresh_token": "ref"})

    tokens = exchange_authorization_code(
        _Client(),  # type: ignore[arg-type]
        token_endpoint=CODEX_OAUTH_TOKEN_URL,
        authorization_code="ac-1",
        code_verifier="cv-1",
    )
    assert seen["url"] == CODEX_OAUTH_TOKEN_URL
    assert seen["data"] == {
        "grant_type": "authorization_code",
        "client_id": CODEX_OAUTH_CLIENT_ID,
        "code": "ac-1",
        "code_verifier": "cv-1",
        "redirect_uri": "https://auth.openai.com/deviceauth/callback",
    }
    assert tokens["access_token"] == "tok"


def test_exchange_failure_raises():
    class _Client:
        def post(self, url, **kwargs):
            return _Resp(400, text="invalid_grant")

    with pytest.raises(AuthError, match="400"):
        exchange_authorization_code(
            _Client(),  # type: ignore[arg-type]
            token_endpoint=CODEX_OAUTH_TOKEN_URL,
            authorization_code="ac-1",
            code_verifier="cv-1",
        )


def test_exchange_requires_a_refresh_token():
    class _Client:
        def post(self, url, **kwargs):
            return _Resp(200, {"access_token": "tok"})

    with pytest.raises(AuthError, match="refresh_token"):
        exchange_authorization_code(
            _Client(),  # type: ignore[arg-type]
            token_endpoint=CODEX_OAUTH_TOKEN_URL,
            authorization_code="ac-1",
            code_verifier="cv-1",
        )


# --- the CLI verb -----------------------------------------------------------


class _LoginClient:
    """Every response the three-step flow needs. Never touches the network."""

    def __init__(self, *args, **kwargs):
        self.urls: list[str] = []
        self.interval = "1"
        self.pending = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, **kwargs):
        url = str(url)
        self.urls.append(url)
        if url == CODEX_OAUTH_DEVICE_CODE_URL:
            return _Resp(
                200,
                {
                    "device_auth_id": "dev-1",
                    "user_code": "ABCD-1234",
                    "interval": self.interval,
                },
            )
        if url == CODEX_OAUTH_DEVICE_TOKEN_URL:
            if self.pending:
                self.pending -= 1
                return _Resp(403, text="")
            return _Resp(200, {"authorization_code": "ac-1", "code_verifier": "cv-1"})
        if url == CODEX_OAUTH_TOKEN_URL:
            return _Resp(200, {"access_token": "tok-codex", "refresh_token": "ref-codex"})
        raise AssertionError(f"unexpected URL {url}")


def _run_login(monkeypatch, tmp_path, *, interval="1", pending=0):
    vault = tmp_path / "auth.json"
    config = tmp_path / "config.yaml"
    hermes = tmp_path / "hermes-auth.json"
    hermes.write_text('{"credential_pool": {"openai-codex": {}}}', encoding="utf-8")
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(vault))
    monkeypatch.setattr("otel_agent.commands.auth_cmd.HERMES_AUTH", hermes)
    monkeypatch.setattr("otel_agent.commands.auth_cmd.webbrowser.open", lambda url: False)
    monkeypatch.setattr("otel_agent.commands.auth_cmd.is_remote_session", lambda: True)

    def _must_not_read(*args, **kwargs):
        raise AssertionError("the device-code login must not read a sibling CLI's store")

    monkeypatch.setattr("otel_agent.commands.auth_cmd.read_grant_source", _must_not_read)
    monkeypatch.setattr("otel_agent.commands.auth_cmd.adopt_grant", _must_not_read)

    sleeps: list[float] = []
    monkeypatch.setattr("otel_agent.codex_oauth.time.sleep", sleeps.append)

    def _client(*args, **kwargs):
        client = _LoginClient()
        client.interval = interval
        client.pending = pending
        return client

    monkeypatch.setattr("otel_agent.commands.auth_cmd.httpx.Client", _client)
    handle_auth(Namespace(auth_action="login-codex", config=str(config), no_browser=True))
    return vault, config, hermes, sleeps


def test_login_codex_writes_a_self_owned_vault_entry(tmp_path, monkeypatch):
    vault, config, hermes, _ = _run_login(monkeypatch, tmp_path)

    stored = json.loads(vault.read_text())
    entry = stored["providers"]["codex"]
    assert entry["auth"] == "codex-oauth"
    assert entry["imported_from"] == "device-code"
    assert entry["client_id"] == CODEX_OAUTH_CLIENT_ID
    assert entry["discovery"]["token_endpoint"] == CODEX_OAUTH_TOKEN_URL
    assert entry["tokens"]["access_token"] == "tok-codex"
    assert entry["tokens"]["refresh_token"] == "ref-codex"
    assert vault.stat().st_mode & 0o777 == 0o600

    provider = Config(config).get_provider("codex")
    assert provider is not None
    assert provider.auth == "codex-oauth"
    assert provider.base_url == "https://chatgpt.com/backend-api/codex"

    # The sibling CLI's store is read by nobody and written by nobody.
    assert hermes.read_text() == '{"credential_pool": {"openai-codex": {}}}'


def test_login_codex_prints_the_verification_url_and_code(tmp_path, monkeypatch, capsys):
    _run_login(monkeypatch, tmp_path)
    out = capsys.readouterr().out
    assert CODEX_OAUTH_VERIFICATION_URL in out
    assert "ABCD-1234" in out


def test_login_codex_polls_the_string_interval_before_succeeding(tmp_path, monkeypatch):
    _, _, _, sleeps = _run_login(monkeypatch, tmp_path, interval="3", pending=2)
    assert sleeps == [3, 3]


def test_login_codex_floors_a_zero_interval(tmp_path, monkeypatch):
    _, _, _, sleeps = _run_login(monkeypatch, tmp_path, interval="0", pending=1)
    assert sleeps == [1]


def test_login_codex_reports_a_disabled_device_flow(tmp_path, monkeypatch, capsys):
    vault = tmp_path / "auth.json"
    config = tmp_path / "config.yaml"
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(vault))

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            return _Resp(404, text="device auth is not enabled")

    monkeypatch.setattr("otel_agent.commands.auth_cmd.httpx.Client", _Client)

    with pytest.raises(SystemExit) as excinfo:
        handle_auth(Namespace(auth_action="login-codex", config=str(config), no_browser=True))
    assert excinfo.value.code == 1
    assert "device auth is not enabled" in capsys.readouterr().out
    assert not vault.exists()

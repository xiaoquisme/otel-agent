"""Tests for xAI device-code request/poll and login CLI."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from otel_agent.auth_vault import AuthError
from otel_agent.commands.auth_cmd import handle_auth
from otel_agent.config import Config
from otel_agent.xai_oauth import poll_device_token, request_device_code


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


def test_request_device_code_requires_fields():
    class _Client:
        def post(self, *a, **k):
            return _Resp(200, {"device_code": "d"})

    with pytest.raises(AuthError, match="missing fields"):
        request_device_code(_Client())  # type: ignore[arg-type]


def test_poll_pending_then_success():
    calls = {"n": 0}

    class _Client:
        def post(self, *a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                return _Resp(400, {"error": "authorization_pending"})
            return _Resp(200, {"access_token": "a", "refresh_token": "r"})

    sleeps: list[float] = []
    clock = {"t": 0.0}

    def mono():
        return clock["t"]

    def sleep(seconds):
        sleeps.append(seconds)
        clock["t"] += seconds

    tokens = poll_device_token(
        _Client(),  # type: ignore[arg-type]
        token_endpoint="https://auth.x.ai/oauth2/token",
        device_code="dev",
        expires_in=30,
        poll_interval=2,
        sleep=sleep,
        monotonic=mono,
    )
    assert tokens["access_token"] == "a"
    assert sleeps == [2]


def test_poll_slow_down_bumps_interval():
    calls = {"n": 0}

    class _Client:
        def post(self, *a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                return _Resp(400, {"error": "slow_down"})
            return _Resp(200, {"access_token": "a", "refresh_token": "r"})

    sleeps: list[float] = []
    clock = {"t": 0.0}
    poll_device_token(
        _Client(),  # type: ignore[arg-type]
        token_endpoint="https://auth.x.ai/oauth2/token",
        device_code="dev",
        expires_in=30,
        poll_interval=2,
        sleep=lambda s: sleeps.append(s) or clock.__setitem__("t", clock["t"] + s),
        monotonic=lambda: clock["t"],
    )
    assert sleeps == [3]


def test_poll_denied():
    class _Client:
        def post(self, *a, **k):
            return _Resp(400, {"error": "access_denied", "error_description": "nope"})

    with pytest.raises(AuthError, match="nope"):
        poll_device_token(
            _Client(),  # type: ignore[arg-type]
            token_endpoint="https://auth.x.ai/oauth2/token",
            device_code="dev",
            expires_in=5,
            poll_interval=1,
            sleep=lambda s: None,
            monotonic=lambda: 0.0 if not hasattr(poll_device_token, "_") else 0.0,
        )


def test_poll_timeout():
    class _Client:
        def post(self, *a, **k):
            return _Resp(400, {"error": "authorization_pending"})

    clock = {"t": 0.0}

    def sleep(seconds):
        clock["t"] += 100

    with pytest.raises(AuthError, match="Timed out"):
        poll_device_token(
            _Client(),  # type: ignore[arg-type]
            token_endpoint="https://auth.x.ai/oauth2/token",
            device_code="dev",
            expires_in=1,
            poll_interval=1,
            sleep=sleep,
            monotonic=lambda: clock["t"],
        )


def test_poll_missing_refresh():
    class _Client:
        def post(self, *a, **k):
            return _Resp(200, {"access_token": "a"})

    with pytest.raises(AuthError, match="refresh_token"):
        poll_device_token(
            _Client(),  # type: ignore[arg-type]
            token_endpoint="https://auth.x.ai/oauth2/token",
            device_code="dev",
            expires_in=10,
            poll_interval=1,
            sleep=lambda s: None,
            monotonic=lambda: 0.0,
        )


def test_login_saves_vault_not_hermes(tmp_path, monkeypatch):
    vault = tmp_path / "auth.json"
    config = tmp_path / "config.yaml"
    hermes = tmp_path / "hermes-auth.json"
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(vault))
    monkeypatch.setattr("otel_agent.commands.auth_cmd.HERMES_AUTH", hermes)
    monkeypatch.setattr("otel_agent.commands.auth_cmd.webbrowser.open", lambda url: False)
    monkeypatch.setattr("otel_agent.commands.auth_cmd.is_remote_session", lambda: True)

    class _Client:
        def __init__(self, *a, **k):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return _Resp(200, {"token_endpoint": "https://auth.x.ai/oauth2/token"})

        def post(self, url, *a, **k):
            self.calls += 1
            if "device/code" in str(url):
                return _Resp(
                    200,
                    {
                        "device_code": "dev",
                        "user_code": "ABCD",
                        "verification_uri": "https://auth.x.ai/activate",
                        "verification_uri_complete": "https://auth.x.ai/activate?user_code=ABCD",
                        "expires_in": 10,
                        "interval": 1,
                    },
                )
            return _Resp(200, {"access_token": "tok-login", "refresh_token": "ref-login"})

    monkeypatch.setattr("otel_agent.commands.auth_cmd.httpx.Client", _Client)
    monkeypatch.setattr("otel_agent.xai_oauth.time.sleep", lambda s: None)

    handle_auth(Namespace(auth_action="login", config=str(config), no_browser=True))

    stored = json.loads(vault.read_text())
    assert stored["providers"]["xai"]["imported_from"] == "device-code"
    assert stored["providers"]["xai"]["tokens"]["access_token"] == "tok-login"
    assert vault.stat().st_mode & 0o777 == 0o600
    assert not hermes.exists()
    provider = Config(config).get_provider("xai")
    assert provider is not None
    assert provider.auth == "xai-oauth"

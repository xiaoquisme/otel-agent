"""Tests for auto-mode routing — server integration tests (U3, U7)."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from otel_agent.config import Config
from otel_agent.logger import TelemetryLogger
from otel_agent.server import create_app

# Save the real post method before any patching
_REAL_POST = httpx.AsyncClient.post


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_config_with_providers(td: str) -> Config:
    config_path = Path(td) / "config.yaml"
    config_path.write_text(
        "providers:\n"
        "  - name: cheap-provider\n"
        "    base_url: https://api.cheap.com/v1\n"
        "    api_key: cheap-key\n"
        "    api_format: openai\n"
        "    cost_per_1k_input: 0.001\n"
        "    cost_per_1k_output: 0.002\n"
        "    default_model: cheap-model\n"
        "  - name: expensive-provider\n"
        "    base_url: https://api.expensive.com/v1\n"
        "    api_key: expensive-key\n"
        "    api_format: openai\n"
        "    cost_per_1k_input: 0.03\n"
        "    cost_per_1k_output: 0.06\n"
        "    default_model: expensive-model\n"
    )
    return Config(config_path)


def _fake_upstream_response(model="cheap-model", content="Hello"):
    body = {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "model": model,
    }
    return httpx.Response(
        status_code=200,
        json=body,
        headers={"content-type": "application/json"},
        request=httpx.Request("POST", "https://api.cheap.com/v1/chat/completions"),
    )


def _smart_mock_post(responses=None, error=None):
    """Mock that only intercepts the server's internal client,
    letting the test client (ASGITransport) pass through to the real post."""
    _state = {"call_count": 0, "responses": responses or [], "error": error}

    async def mock_post(self, *args, **kwargs):
        if isinstance(self._transport, httpx.ASGITransport):
            return await _REAL_POST(self, *args, **kwargs)
        if _state["error"]:
            raise _state["error"]
        idx = _state["call_count"]
        _state["call_count"] += 1
        if idx < len(_state["responses"]):
            return _state["responses"][idx]
        return _fake_upstream_response()

    return mock_post


# ------------------------------------------------------------------
# AE1: Basic Auto Routing
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_auto_mode_basic_routing():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        config = _make_config_with_providers(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        with patch.object(httpx.AsyncClient, "post", _smart_mock_post(responses=[_fake_upstream_response()])):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "auto", "messages": [{"role": "user", "content": "What is 2+2?"}]},
                )
                body = resp.json()

        telemetry.close()
        assert resp.status_code == 200
        assert body["choices"][0]["message"]["content"] == "Hello"
        assert "X-Routed-Provider" in resp.headers
        assert resp.headers["X-Routed-Tier"] == "simple"
        assert resp.headers["X-Routed-Reason"] in ("cost_optimized", "session_sticky")


# ------------------------------------------------------------------
# AE2: Complex Task Routing
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_auto_mode_complex_task():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        config = _make_config_with_providers(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        with patch.object(httpx.AsyncClient, "post", _smart_mock_post(
            responses=[_fake_upstream_response(content="def merge(a,b): ...")]
        )):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "auto", "messages": [
                        {"role": "system", "content": "You are a coding assistant"},
                        {"role": "user", "content": "Write a function:\n```python\n# code\n```"},
                    ]},
                )

        telemetry.close()
        assert resp.status_code == 200
        assert resp.headers["X-Routed-Tier"] == "complex"


# ------------------------------------------------------------------
# AE3: Provider Fallback
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_auto_mode_provider_fallback():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        config = _make_config_with_providers(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        counter = {"n": 0}

        async def fallback_post(self, *args, **kwargs):
            if isinstance(self._transport, httpx.ASGITransport):
                return await _REAL_POST(self, *args, **kwargs)
            counter["n"] += 1
            if counter["n"] == 1:
                raise httpx.ConnectError("Connection refused")
            return _fake_upstream_response(model="expensive-model", content="fallback ok")

        with patch.object(httpx.AsyncClient, "post", fallback_post):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
                )
                body = resp.json()

        telemetry.close()
        assert resp.status_code == 200
        assert body["choices"][0]["message"]["content"] == "fallback ok"
        assert "X-Routed-Fallback-Depth" in resp.headers
        assert resp.headers["X-Routed-Fallback-Depth"] == "1"
        assert counter["n"] == 2


# ------------------------------------------------------------------
# AE4: Session Stickiness
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_auto_mode_session_sticky():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        config = _make_config_with_providers(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        with patch.object(httpx.AsyncClient, "post", _smart_mock_post(
            responses=[_fake_upstream_response() for _ in range(3)]
        )):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                providers = []
                for i in range(3):
                    resp = await client.post(
                        "/v1/chat/completions",
                        json={"model": "auto", "messages": [{"role": "user", "content": f"msg {i}"}]},
                        headers={"X-Session-ID": "sticky-123"},
                    )
                    providers.append(resp.headers.get("X-Routed-Provider"))

        telemetry.close()
        assert len(set(providers)) == 1, f"Session not sticky: {providers}"


# ------------------------------------------------------------------
# AE5: Explicit Model Unchanged
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_explicit_model_bypasses_auto():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        config = _make_config_with_providers(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        with patch.object(httpx.AsyncClient, "post", _smart_mock_post(responses=[_fake_upstream_response()])):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "cheap-provider/cheap-model", "messages": [{"role": "user", "content": "hi"}]},
                )

        telemetry.close()
        assert "X-Routed-Provider" not in resp.headers
        assert "X-Routed-Tier" not in resp.headers


# ------------------------------------------------------------------
# No providers -> 503
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_auto_mode_no_providers_returns_503():
    with tempfile.TemporaryDirectory() as td:
        config_path = Path(td) / "config.yaml"
        config_path.write_text("providers: []\n")
        config = Config(config_path)
        db_path = Path(td) / "test.duckdb"
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        from httpx import ASGITransport
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
            )

        telemetry.close()
        assert resp.status_code == 503
        assert "No providers available" in resp.json()["error"]["message"]


# ------------------------------------------------------------------
# All providers fail -> 502
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_auto_mode_all_providers_fail_returns_502():
    with tempfile.TemporaryDirectory() as td:
        config = _make_config_with_providers(td)
        db_path = Path(td) / "test.duckdb"
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        async def always_fail(self, *args, **kwargs):
            if isinstance(self._transport, httpx.ASGITransport):
                return await _REAL_POST(self, *args, **kwargs)
            raise httpx.ConnectError("Connection refused")

        with patch.object(httpx.AsyncClient, "post", always_fail):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
                )

        telemetry.close()
        assert resp.status_code == 502
        error_msg = resp.json()["error"]["message"]
        assert "All providers failed" in error_msg or "Max fallback depth" in error_msg


# ------------------------------------------------------------------
# Routing decision in telemetry
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_auto_mode_routing_decision_in_telemetry():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        config = _make_config_with_providers(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        with patch.object(httpx.AsyncClient, "post", _smart_mock_post(responses=[_fake_upstream_response()])):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
                )

        telemetry.close()

        import duckdb
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute("SELECT request_headers FROM requests").fetchone()
        conn.close()

        assert row is not None
        headers = json.loads(row[0])
        assert "x-routing-decision" in headers
        decision = json.loads(headers["x-routing-decision"])
        assert "tier" in decision
        assert "provider" in decision
        assert "reason" in decision

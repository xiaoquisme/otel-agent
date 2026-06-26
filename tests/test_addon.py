import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from otel_agent.addon import TelemetryAddon
from otel_agent.logger import TelemetryLogger


def _make_flow(method="POST", url="https://api.openai.com/v1/chat/completions",
               req_body='{"model":"gpt-4"}', resp_body='{"choices":[]}',
               resp_status=200):
    """Create a mock mitmproxy flow."""
    flow = MagicMock()
    flow.request.method = method
    flow.request.url = url
    flow.request.host = "api.openai.com"
    flow.request.headers = {"Authorization": "Bearer sk-test"}
    flow.request.get_content.return_value = req_body.encode()
    flow.request.scheme = "https"
    flow.request.port = 443
    flow.response = MagicMock()
    flow.response.status_code = resp_status
    flow.response.headers = {"content-type": "application/json"}
    flow.response.get_content.return_value = resp_body.encode()
    flow.response.timestamp_start = 1000.0
    flow.response.timestamp_end = 1001.5
    return flow


def test_addon_logs_request():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        addon = TelemetryAddon(logger, upstream_override="")

        flow = _make_flow()
        addon.response(flow)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT method, request_body FROM requests").fetchone()
        conn.close()
        assert row[0] == "POST"
        assert "gpt-4" in row[1]
        logger.close()


def test_addon_calculates_latency():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        addon = TelemetryAddon(logger, upstream_override="")

        flow = _make_flow()
        flow.response.timestamp_start = 1000.0
        flow.response.timestamp_end = 1001.5
        addon.response(flow)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT latency_ms FROM requests").fetchone()
        conn.close()
        assert row[0] == 1500.0  # (1001.5 - 1000.0) * 1000
        logger.close()


def test_addon_injects_openai_key():
    """API key for openai.com should be injected as Authorization: Bearer sk-xxx"""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        addon = TelemetryAddon(
            logger, upstream_override="",
            api_keys={"openai.com": "sk-test123"},
        )

        flow = _make_flow(url="https://api.openai.com/v1/chat/completions")
        flow.request.host = "api.openai.com"
        flow.request.headers = {}  # no auth header
        addon.request(flow)

        assert flow.request.headers["Authorization"] == "Bearer sk-test123"
        logger.close()


def test_addon_injects_anthropic_key():
    """API key for anthropic.com should be injected as x-api-key"""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        addon = TelemetryAddon(
            logger, upstream_override="",
            api_keys={"anthropic.com": "sk-ant-test123"},
        )

        flow = _make_flow(url="https://api.anthropic.com/v1/messages")
        flow.request.host = "api.anthropic.com"
        flow.request.headers = {}
        addon.request(flow)

        assert flow.request.headers["x-api-key"] == "sk-ant-test123"
        logger.close()


def test_addon_overrides_existing_key():
    """If client sends a key, proxy should override it."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        addon = TelemetryAddon(
            logger, upstream_override="",
            api_keys={"openai.com": "sk-real-key"},
        )

        flow = _make_flow()
        flow.request.host = "api.openai.com"
        flow.request.headers = {"Authorization": "Bearer sk-client-garbage"}
        addon.request(flow)

        assert flow.request.headers["Authorization"] == "Bearer sk-real-key"
        logger.close()


def test_addon_no_key_no_change():
    """If no key configured for a host, leave headers untouched."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        addon = TelemetryAddon(
            logger, upstream_override="",
            api_keys={"openai.com": "sk-test"},
        )

        flow = _make_flow(url="https://api.cohere.com/v1/chat")
        flow.request.host = "api.cohere.com"
        flow.request.headers = {"Authorization": "Bearer cohere-key"}
        addon.request(flow)

        assert flow.request.headers["Authorization"] == "Bearer cohere-key"
        logger.close()


def test_addon_injects_after_upstream_rewrite():
    """Key injection should work even after upstream rewrite."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        addon = TelemetryAddon(
            logger,
            upstream_override="https://api.anthropic.com",
            api_keys={"anthropic.com": "sk-ant-xxx"},
        )

        flow = _make_flow(url="https://api.openai.com/v1/chat/completions")
        flow.request.host = "api.openai.com"
        flow.request.headers = {}
        addon.request(flow)

        # After rewrite, host should be anthropic.com
        assert flow.request.host == "api.anthropic.com"
        assert flow.request.headers["x-api-key"] == "sk-ant-xxx"
        logger.close()

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
    flow.request.headers = {"Authorization": "Bearer sk-test"}
    flow.request.get_content.return_value = req_body.encode()
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

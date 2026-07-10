"""Tests for _log_telemetry and request/response body logging."""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import duckdb

from otel_agent.logger import TelemetryLogger
from otel_agent.server import _log_telemetry


def _make_provider(name: str = "openai", base_url: str = "https://api.openai.com") -> MagicMock:
    p = MagicMock()
    p.name = name
    p.base_url = base_url
    return p


def _make_request(method: str = "POST", url: str = "http://localhost:8080/v1/chat/completions") -> MagicMock:
    r = MagicMock()
    r.method = method
    r.url = url
    r.headers = {"content-type": "application/json"}
    return r


def test_log_telemetry_stores_request_body():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.duckdb"
        telemetry = TelemetryLogger(db)
        body_str = json.dumps({"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]})
        _log_telemetry(
            telemetry, _make_request(), 200, {"choices": []}, 100.0,
            _make_provider(), request_body=body_str,
        )
        telemetry.close()
        conn = duckdb.connect(str(db), read_only=True)
        row = conn.execute("SELECT request_body FROM requests").fetchone()
        conn.close()
        parsed = json.loads(row[0])
        assert parsed["model"] == "gpt-4"


def test_log_telemetry_stores_response_headers():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.duckdb"
        telemetry = TelemetryLogger(db)
        headers = {"content-type": "application/json", "x-request-id": "abc-123"}
        _log_telemetry(
            telemetry, _make_request(), 200, {}, 100.0,
            _make_provider(), resp_headers=headers,
        )
        telemetry.close()
        conn = duckdb.connect(str(db), read_only=True)
        row = conn.execute("SELECT response_headers FROM requests").fetchone()
        conn.close()
        parsed = json.loads(row[0])
        assert parsed["x-request-id"] == "abc-123"


def test_log_telemetry_redacts_sensitive_headers():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.duckdb"
        telemetry = TelemetryLogger(db)
        headers = {"authorization": "Bearer sk-secret", "content-type": "application/json"}
        _log_telemetry(
            telemetry, _make_request(), 200, {}, 100.0,
            _make_provider(), resp_headers=headers,
        )
        telemetry.close()
        conn = duckdb.connect(str(db), read_only=True)
        row = conn.execute("SELECT response_headers FROM requests").fetchone()
        conn.close()
        parsed = json.loads(row[0])
        assert parsed["authorization"] == "[REDACTED]"
        assert parsed["content-type"] == "application/json"


def test_log_telemetry_empty_body_when_log_body_false():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.duckdb"
        telemetry = TelemetryLogger(db)
        _log_telemetry(
            telemetry, _make_request(), 200, {}, 100.0,
            _make_provider(), request_body="should not be stored", log_body=False,
        )
        telemetry.close()
        conn = duckdb.connect(str(db), read_only=True)
        row = conn.execute("SELECT request_body FROM requests").fetchone()
        conn.close()
        assert row[0] == ""


def test_log_telemetry_truncates_long_body():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.duckdb"
        telemetry = TelemetryLogger(db)
        long_body = "x" * 550_000
        _log_telemetry(
            telemetry, _make_request(), 200, {}, 100.0,
            _make_provider(), request_body=long_body,
        )
        telemetry.close()
        conn = duckdb.connect(str(db), read_only=True)
        row = conn.execute("SELECT request_body FROM requests").fetchone()
        conn.close()
        assert len(row[0]) == 500_000

import json
import sqlite3
import tempfile
from pathlib import Path
from otel_agent.logger import TelemetryLogger


def test_creates_db_and_tables():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        logger.close()
        conn = sqlite3.connect(str(db_path))
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        assert "requests" in tables


def test_log_request_inserts_row():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        logger.log_request(
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            request_headers={"Authorization": "Bearer sk-test", "Content-Type": "application/json"},
            request_body='{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}',
            response_status=200,
            response_headers={"content-type": "application/json"},
            response_body='{"choices":[{"message":{"content":"hello"}}]}',
            latency_ms=1234.5,
            upstream="https://api.openai.com",
        )
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT method, url, upstream, latency_ms FROM requests").fetchone()
        conn.close()
        assert row[0] == "POST"
        assert "openai.com" in row[1]
        assert row[2] == "https://api.openai.com"
        assert row[3] == 1234.5


def test_log_preserves_full_payload():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        body = json.dumps({"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]})
        logger.log_request(
            method="POST", url="https://api.openai.com/v1/chat/completions",
            request_headers={}, request_body=body,
            response_status=200, response_headers={},
            response_body='{"choices":[]}', latency_ms=100.0,
            upstream="https://api.openai.com",
        )
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT request_body FROM requests").fetchone()
        conn.close()
        parsed = json.loads(row[0])
        assert parsed["model"] == "gpt-4"


def test_redact_sensitive_headers():
    from otel_agent.logger import redact_sensitive_headers

    headers = {
        "content-type": "application/json",
        "Authorization": "Bearer sk-test",
        "X-Api-Key": "key-123",
        "x-request-id": "abc",
        "Set-Cookie": "session=xyz",
    }
    result = redact_sensitive_headers(headers)
    assert result["content-type"] == "application/json"
    assert result["Authorization"] == "[REDACTED]"
    assert result["X-Api-Key"] == "[REDACTED]"
    assert result["x-request-id"] == "abc"
    assert result["Set-Cookie"] == "[REDACTED]"


def test_redact_preserves_non_sensitive():
    from otel_agent.logger import redact_sensitive_headers

    headers = {"content-type": "text/plain", "x-custom": "value"}
    result = redact_sensitive_headers(headers)
    assert result == headers

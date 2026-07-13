"""Tests for TelemetryLogger with DuckDB backend."""
import json
import tempfile
from pathlib import Path
import duckdb
from otel_agent.logger import TelemetryLogger, redact_sensitive_headers

def test_creates_db_and_tables():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        logger = TelemetryLogger(db_path)
        logger.close()
        conn = duckdb.connect(str(db_path), read_only=True)
        tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()]
        conn.close()
        assert "requests" in tables


def test_log_request_inserts_row():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
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
        logger.close()
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute("SELECT method, url, upstream, latency_ms FROM requests").fetchone()
        conn.close()
        assert row[0] == "POST"
        assert "openai.com" in row[1]
        assert row[2] == "https://api.openai.com"
        assert row[3] == 1234.5


def test_log_preserves_full_payload():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        logger = TelemetryLogger(db_path)
        body = json.dumps({"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]})
        logger.log_request(
            method="POST", url="https://api.openai.com/v1/chat/completions",
            request_headers={}, request_body=body,
            response_status=200, response_headers={},
            response_body='{"choices":[]}', latency_ms=100.0,
            upstream="https://api.openai.com",
        )
        logger.close()
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute("SELECT request_body FROM requests").fetchone()
        conn.close()
        parsed = json.loads(row[0])
        assert parsed["model"] == "gpt-4"


def test_redact_sensitive_headers():
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
    headers = {"content-type": "text/plain", "x-custom": "value"}
    result = redact_sensitive_headers(headers)
    assert result == headers


# ------------------------------------------------------------------
# T004: Legacy-schema upgrade and analytics-column persistence
# ------------------------------------------------------------------

def _create_legacy_duckdb(db_path):
    """Create a DuckDB with the old schema (no analytics columns)."""
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE SEQUENCE IF NOT EXISTS requests_id_seq START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER DEFAULT nextval('requests_id_seq') PRIMARY KEY,
            timestamp TEXT NOT NULL,
            method TEXT NOT NULL,
            url TEXT NOT NULL,
            upstream TEXT,
            request_headers TEXT,
            request_body TEXT,
            response_status INTEGER,
            response_headers TEXT,
            response_body TEXT,
            latency_ms DOUBLE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp)")
    conn.execute("INSERT INTO requests (timestamp, method, url, response_status, latency_ms) VALUES ('2026-01-01T00:00:00Z', 'GET', 'http://example.com', 200, 10.0)")
    conn.commit()
    conn.close()


def test_duckdb_legacy_schema_upgrade(tmp_path):
    """Calling TelemetryLogger.initialize() on a legacy DB adds analytics columns."""
    db_path = tmp_path / "legacy.duckdb"
    _create_legacy_duckdb(db_path)
    logger = TelemetryLogger(db_path)
    logger.close()
    conn = duckdb.connect(str(db_path), read_only=True)
    columns = [r[0] for r in conn.execute("DESCRIBE requests").fetchall()]
    conn.close()
    assert "model_name" in columns
    assert "input_tokens" in columns
    assert "output_tokens" in columns
    assert "total_tokens" in columns


def test_duckdb_analytics_columns_persist(tmp_path):
    """Records written with analytics fields are retrievable."""
    db_path = tmp_path / "analytics.duckdb"
    logger = TelemetryLogger(db_path)
    logger.log_request(
        method="POST", url="http://test.com",
        request_headers={}, request_body="",
        response_status=200, response_headers={},
        response_body="{}", latency_ms=1.0,
        upstream="http://test.com",
        model_name="openai/gpt-4o",
        input_tokens=100, output_tokens=50, total_tokens=150,
    )
    logger.close()
    conn = duckdb.connect(str(db_path), read_only=True)
    row = conn.execute("SELECT model_name, input_tokens, output_tokens, total_tokens FROM requests").fetchone()
    conn.close()
    assert row[0] == "openai/gpt-4o"
    assert row[1] == 100
    assert row[2] == 50
    assert row[3] == 150


def test_duckdb_null_analytics_fields(tmp_path):
    """Records without analytics fields have NULL analytics values."""
    db_path = tmp_path / "null_analytics.duckdb"
    logger = TelemetryLogger(db_path)
    logger.log_request(
        method="GET", url="http://test.com",
        request_headers={}, request_body="",
        response_status=200, response_headers={},
        response_body="{}", latency_ms=1.0,
        upstream="http://test.com",
    )
    logger.close()
    conn = duckdb.connect(str(db_path), read_only=True)
    row = conn.execute("SELECT model_name, input_tokens, output_tokens, total_tokens FROM requests").fetchone()
    conn.close()
    assert row[0] is None
    assert row[1] is None
    assert row[2] is None
    assert row[3] is None

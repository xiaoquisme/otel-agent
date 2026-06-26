import tempfile
from pathlib import Path
from otel_agent.logger import TelemetryLogger
from otel_agent.viewer import query_requests, format_request


def test_query_returns_all():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        logger = TelemetryLogger(db)
        logger.log_request("POST", "https://api.openai.com/v1/chat/completions",
                           {}, '{"model":"gpt-4"}', 200, {}, '{"choices":[]}',
                           100.0, "https://api.openai.com")
        logger.log_request("POST", "https://api.anthropic.com/v1/messages",
                           {}, '{"model":"claude-3"}', 200, {}, '{"content":[]}',
                           200.0, "https://api.anthropic.com")
        logger.close()

        rows = query_requests(db)
        assert len(rows) == 2


def test_query_filters_by_upstream():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        logger = TelemetryLogger(db)
        logger.log_request("POST", "https://api.openai.com/v1/chat/completions",
                           {}, '{}', 200, {}, '{}', 100.0, "https://api.openai.com")
        logger.log_request("POST", "https://api.anthropic.com/v1/messages",
                           {}, '{}', 200, {}, '{}', 200.0, "https://api.anthropic.com")
        logger.close()

        rows = query_requests(db, upstream_filter="openai")
        assert len(rows) == 1


def test_format_request():
    row = {
        "id": 1, "timestamp": "2026-06-26T10:00:00",
        "method": "POST", "url": "https://api.openai.com/v1/chat/completions",
        "upstream": "https://api.openai.com",
        "request_body": '{"model":"gpt-4"}',
        "response_status": 200, "latency_ms": 123.4,
    }
    text = format_request(row)
    assert "POST" in text
    assert "200" in text
    assert "gpt-4" in text

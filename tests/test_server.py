"""Tests for _log_telemetry and request/response body logging."""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import httpx
import pytest

from otel_agent import server
from otel_agent.config import Config
from otel_agent.logger import TelemetryLogger
from otel_agent.server import _log_telemetry, create_app


# ------------------------------------------------------------------
# Reusable fixture helpers (T002)
# ------------------------------------------------------------------

def _make_openai_usage_response(
    *, input_tokens: int = 10, output_tokens: int = 5,
    total_tokens: int | None = None,
) -> dict:
    """Build an OpenAI-shaped response body with usage."""
    usage = {"prompt_tokens": input_tokens, "completion_tokens": output_tokens}
    if total_tokens is not None:
        usage["total_tokens"] = total_tokens
    else:
        usage["total_tokens"] = input_tokens + output_tokens
    return {"choices": [{"message": {"content": "ok"}}], "usage": usage, "model": "gpt-4"}


def _make_anthropic_usage_response(
    *, input_tokens: int = 10, output_tokens: int = 5,
) -> dict:
    """Build an Anthropic-shaped response body with usage."""
    return {
        "content": [{"type": "text", "text": "ok"}],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "model": "claude-sonnet-4-20250514",
    }


def _make_no_usage_response() -> dict:
    """Build a response body with no usage data."""
    return {"choices": [{"message": {"content": "ok"}}]}


def _make_malformed_usage_response() -> dict:
    """Build a response with invalid usage values."""
    return {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": -1, "completion_tokens": True, "total_tokens": "bad"},
    }


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


# ------------------------------------------------------------------
# Regression tests for streaming telemetry bug (019)
# ------------------------------------------------------------------


class _FakeSSEStream:
    """Mock async context manager that yields SSE lines for streaming tests."""

    def __init__(self, chunks: list[dict], done: bool = True):
        self._chunks = chunks
        self._done = done
        self.headers = {"content-type": "text/event-stream"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def aiter_lines(self):
        for chunk in self._chunks:
            yield f"data: {json.dumps(chunk)}"
        if self._done:
            yield "data: [DONE]"


class _FakeStreamMethod:
    """Mock for httpx.AsyncClient.stream() that returns an async context manager.

    ``httpx.AsyncClient.stream()`` is a *sync* method that returns an
    ``_AsyncStreamContextManager`` — NOT a coroutine.  So our mock must
    also return the context manager synchronously.
    """

    def __init__(self, chunks: list[dict], done: bool = True):
        self._stream = _FakeSSEStream(chunks, done)

    def __call__(self, *args, **kwargs):
        return self._stream


def _make_test_config(td: str) -> Config:
    """Create a Config backed by a temp YAML file with a test provider."""
    config_path = Path(td) / "config.yaml"
    config_path.write_text(
        "providers:\n"
        "  - name: openai\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key: test-key\n"
        "    api_format: openai\n"
    )
    return Config(config_path)


@pytest.mark.anyio
async def test_streaming_telemetry_logged():
    """Streaming request MUST be logged to telemetry (US1, T003).

    Expected to FAIL before the fix: _log_telemetry() inside the generator
    may not execute reliably.
    """
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        config = _make_test_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        chunks = [
            {"choices": [{"delta": {"content": "Hello"}, "index": 0}]},
            {"choices": [{"delta": {"content": " world"}, "index": 0}]},
        ]
        mock_stream = _FakeStreamMethod(chunks)

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "openai/gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
                )
                # Consume the streaming response
                await resp.aread()

        telemetry.close()

        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute("SELECT response_body FROM requests").fetchone()
        conn.close()

        assert row is not None, "No telemetry record found — streaming request was NOT logged"
        parsed = json.loads(row[0])
        assert parsed["streamed"] is True
        assert "preview" in parsed
        assert len(parsed["preview"]) > 0


@pytest.mark.anyio
async def test_streaming_client_disconnect():
    """Partial stream (client disconnect) MUST still be logged (US1, T004).

    Simulates client reading only part of the stream then disconnecting.
    """
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        config = _make_test_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        chunks = [
            {"choices": [{"delta": {"content": "Hello"}, "index": 0}]},
            {"choices": [{"delta": {"content": " world"}, "index": 0}]},
        ]
        mock_stream = _FakeStreamMethod(chunks)

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "openai/gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
                )
                # Read only the first chunk, then close (simulates disconnect)
                async for line in resp.aiter_lines():
                    break  # read one line then stop
                await resp.aclose()

        # Give the generator a moment to finish (or be abandoned)
        import asyncio
        await asyncio.sleep(0.1)

        telemetry.close()

        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute("SELECT response_body FROM requests").fetchall()
        conn.close()

        assert len(rows) >= 1, (
            "No telemetry record found after client disconnect — "
            "streaming partial request was NOT logged"
        )


@pytest.mark.anyio
async def test_nonstreaming_after_streaming():
    """Non-streaming request MUST be logged after streaming (US2, T005).

    Uses _log_telemetry directly to avoid complex mock chains.
    """
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.duckdb"
        telemetry = TelemetryLogger(db_path)

        # 1) Simulate a streaming request being logged (via _log_telemetry)
        _log_telemetry(
            telemetry, _make_request(), 200,
            {"streamed": True, "preview": "hello world"}, 150.0,
            _make_provider(), request_body='{"model":"openai/gpt-4"}',
        )

        # 2) Simulate a non-streaming request being logged
        _log_telemetry(
            telemetry, _make_request(), 200,
            {"choices": [{"message": {"content": "Hello"}}]}, 80.0,
            _make_provider(), request_body='{"model":"openai/gpt-4"}',
        )

        telemetry.close()

        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute("SELECT response_body FROM requests ORDER BY id").fetchall()
        conn.close()

        assert len(rows) == 2, f"Expected 2 records, got {len(rows)}"

        # First record: streaming
        first = json.loads(rows[0][0])
        assert first["streamed"] is True

        # Second record: non-streaming (no 'streamed' key)
        second = json.loads(rows[1][0])
        assert second.get("streamed") is not True

# ------------------------------------------------------------------
# T012: normalize_usage unit tests
# ------------------------------------------------------------------

def test_normalize_usage_openai_with_total():
    """OpenAI shape with explicit total_tokens."""
    normalize = getattr(server, "normalize_usage")
    result = normalize({"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    assert result == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


def test_normalize_usage_openai_computed_total():
    """OpenAI shape without total_tokens — computed from components."""
    normalize = getattr(server, "normalize_usage")
    result = normalize({"usage": {"prompt_tokens": 10, "completion_tokens": 5}})
    assert result == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


def test_normalize_usage_anthropic():
    """Anthropic shape."""
    normalize = getattr(server, "normalize_usage")
    result = normalize({"usage": {"input_tokens": 20, "output_tokens": 10}})
    assert result == {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30}


def test_normalize_usage_invalid_values():
    """Negative and non-int values produce None."""
    normalize = getattr(server, "normalize_usage")
    result = normalize({"usage": {"prompt_tokens": -1, "completion_tokens": True, "total_tokens": "bad"}})
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["total_tokens"] is None


def test_normalize_usage_missing_usage():
    """Response with no usage key."""
    normalize = getattr(server, "normalize_usage")
    result = normalize({"choices": []})
    assert result == {"input_tokens": None, "output_tokens": None, "total_tokens": None}


def test_normalize_usage_one_component():
    """Only total_tokens provided — components are None."""
    normalize = getattr(server, "normalize_usage")
    result = normalize({"usage": {"total_tokens": 9}})
    assert result == {"input_tokens": None, "output_tokens": None, "total_tokens": 9}


def test_normalize_usage_string_response():
    """Non-dict response returns None for all fields."""
    normalize = getattr(server, "normalize_usage")
    result = normalize("not a dict")
    assert result == {"input_tokens": None, "output_tokens": None, "total_tokens": None}


def test_log_telemetry_stores_model_name():
    """_log_telemetry extracts model from response body."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "model_name.duckdb"
        telemetry = TelemetryLogger(db_path)
        _log_telemetry(
            telemetry, _make_request(), 200,
            {"choices": [], "model": "openai/gpt-4o", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            100.0, _make_provider(),
        )
        telemetry.close()
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute("SELECT model_name, input_tokens, output_tokens, total_tokens FROM requests").fetchone()
        conn.close()
        assert row[0] == "openai/gpt-4o"
        assert row[1] == 10
        assert row[2] == 5
        assert row[3] == 15


def test_log_telemetry_no_model_name():
    """_log_telemetry stores NULL model_name when response has none."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "no_model.duckdb"
        telemetry = TelemetryLogger(db_path)
        _log_telemetry(
            telemetry, _make_request(), 200,
            {"choices": []},
            100.0, _make_provider(),
        )
        telemetry.close()
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute("SELECT model_name FROM requests").fetchone()
        conn.close()
        assert row[0] is None


def test_log_telemetry_log_body_false_no_usage():
    """When log_body=False and no usage, analytics are all NULL."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "no_log.duckdb"
        telemetry = TelemetryLogger(db_path)
        _log_telemetry(
            telemetry, _make_request(), 200,
            {"choices": []},
            100.0, _make_provider(), log_body=False,
        )
        telemetry.close()
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute("SELECT request_body, model_name, input_tokens FROM requests").fetchone()
        conn.close()
        assert row[0] == ""
        assert row[1] is None
        assert row[2] is None


# ------------------------------------------------------------------
# T029: Streaming usage tests (US3)
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_streaming_captures_terminal_usage():
    """Streaming chunks with usage data are captured and persisted."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "stream_usage.duckdb"
        config = _make_test_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        chunks = [
            {"choices": [{"delta": {"content": "Hello"}, "index": 0}]},
            {"choices": [{"delta": {"content": " world"}, "index": 0}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
        ]
        mock_stream = _FakeStreamMethod(chunks)

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "openai/gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
                )
                await resp.aread()

        telemetry.close()
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute("SELECT input_tokens, output_tokens, total_tokens FROM requests").fetchone()
        conn.close()
        assert row is not None, "No telemetry record found"
        assert row[0] == 10
        assert row[1] == 5
        assert row[2] == 15


@pytest.mark.anyio
async def test_streaming_no_usage_all_null():
    """Streaming without usage data produces NULL analytics."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "stream_null.duckdb"
        config = _make_test_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        chunks = [
            {"choices": [{"delta": {"content": "Hello"}, "index": 0}]},
        ]
        mock_stream = _FakeStreamMethod(chunks)

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "openai/gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
                )
                await resp.aread()

        telemetry.close()
        conn = duckdb.connect(str(db_path), read_only=True)
        row = conn.execute("SELECT input_tokens, output_tokens, total_tokens FROM requests").fetchone()
        conn.close()
        assert row[0] is None
        assert row[1] is None
        assert row[2] is None

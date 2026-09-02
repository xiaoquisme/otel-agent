"""Tests for _log_telemetry and request/response body logging."""
import sqlite3
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch


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


def _make_request(method: str = "POST", url: str = "http://localhost:45638/v1/chat/completions") -> MagicMock:
    r = MagicMock()
    r.method = method
    r.url = url
    r.headers = {"content-type": "application/json"}
    return r


def test_log_telemetry_stores_request_body():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.sqlite"
        telemetry = TelemetryLogger(db)
        body_str = json.dumps({"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]})
        _log_telemetry(
            telemetry, _make_request(), 200, {"choices": []}, 100.0,
            _make_provider(), request_body=body_str,
        )
        telemetry.close()
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT request_body FROM requests").fetchone()
        conn.close()
        parsed = json.loads(row[0])
        assert parsed["model"] == "gpt-4"


def test_log_telemetry_stores_response_headers():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.sqlite"
        telemetry = TelemetryLogger(db)
        headers = {"content-type": "application/json", "x-request-id": "abc-123"}
        _log_telemetry(
            telemetry, _make_request(), 200, {}, 100.0,
            _make_provider(), resp_headers=headers,
        )
        telemetry.close()
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT response_headers FROM requests").fetchone()
        conn.close()
        parsed = json.loads(row[0])
        assert parsed["x-request-id"] == "abc-123"


def test_log_telemetry_redacts_sensitive_headers():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.sqlite"
        telemetry = TelemetryLogger(db)
        headers = {"authorization": "Bearer sk-secret", "content-type": "application/json"}
        _log_telemetry(
            telemetry, _make_request(), 200, {}, 100.0,
            _make_provider(), resp_headers=headers,
        )
        telemetry.close()
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT response_headers FROM requests").fetchone()
        conn.close()
        parsed = json.loads(row[0])
        assert parsed["authorization"] == "[REDACTED]"
        assert parsed["content-type"] == "application/json"


def test_log_telemetry_empty_body_when_log_body_false():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.sqlite"
        telemetry = TelemetryLogger(db)
        _log_telemetry(
            telemetry, _make_request(), 200, {}, 100.0,
            _make_provider(), request_body="should not be stored", log_body=False,
        )
        telemetry.close()
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT request_body FROM requests").fetchone()
        conn.close()
        assert row[0] == ""


def test_log_telemetry_truncates_long_body():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.sqlite"
        telemetry = TelemetryLogger(db)
        long_body = "x" * 550_000
        _log_telemetry(
            telemetry, _make_request(), 200, {}, 100.0,
            _make_provider(), request_body=long_body,
        )
        telemetry.close()
        conn = sqlite3.connect(str(db))
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
        self.status_code = 200
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


class _FakeErrorStream:
    """Mock for upstream returning a non-SSE error (e.g. 400 JSON) on a streaming endpoint."""

    def __init__(self, status_code: int, error_body: dict):
        self.status_code = status_code
        self._error_body = error_body
        self.headers = {"content-type": "application/json"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def aread(self):
        return json.dumps(self._error_body).encode()

    async def aiter_lines(self):
        # Non-SSE response — yield nothing (the fix should catch this before iterating)
        yield json.dumps(self._error_body)


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


class _FakeErrorStreamMethod:
    """Mock for httpx.AsyncClient.stream() that returns a non-SSE error response."""

    def __init__(self, status_code: int, error_body: dict):
        self._stream = _FakeErrorStream(status_code, error_body)

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
        db_path = Path(td) / "test.sqlite"
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

        conn = sqlite3.connect(str(db_path))
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
        db_path = Path(td) / "test.sqlite"
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

        conn = sqlite3.connect(str(db_path))
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
        db_path = Path(td) / "test.sqlite"
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

        conn = sqlite3.connect(str(db_path))
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


def test_normalize_usage_null_usage():
    """Response with usage: null (e.g. xiaomi streaming chunks)."""
    normalize = getattr(server, "normalize_usage")
    result = normalize({"choices": [], "usage": None})
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
        db_path = Path(td) / "model_name.sqlite"
        telemetry = TelemetryLogger(db_path)
        _log_telemetry(
            telemetry, _make_request(), 200,
            {"choices": [], "model": "openai/gpt-4o", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            100.0, _make_provider(),
        )
        telemetry.close()
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT model_name, input_tokens, output_tokens, total_tokens FROM requests").fetchone()
        conn.close()
        assert row[0] == "openai/openai/gpt-4o"
        assert row[1] == 10
        assert row[2] == 5
        assert row[3] == 15


def test_log_telemetry_no_model_name():
    """_log_telemetry stores NULL model_name when response has none."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "no_model.sqlite"
        telemetry = TelemetryLogger(db_path)
        _log_telemetry(
            telemetry, _make_request(), 200,
            {"choices": []},
            100.0, _make_provider(),
        )
        telemetry.close()
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT model_name FROM requests").fetchone()
        conn.close()
        assert row[0] is None


def test_log_telemetry_log_body_false_no_usage():
    """When log_body=False and no usage, analytics are all NULL."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "no_log.sqlite"
        telemetry = TelemetryLogger(db_path)
        _log_telemetry(
            telemetry, _make_request(), 200,
            {"choices": []},
            100.0, _make_provider(), log_body=False,
        )
        telemetry.close()
        conn = sqlite3.connect(str(db_path))
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
        db_path = Path(td) / "stream_usage.sqlite"
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
        conn = sqlite3.connect(str(db_path))
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
        db_path = Path(td) / "stream_null.sqlite"
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
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT input_tokens, output_tokens, total_tokens FROM requests").fetchone()
        conn.close()
        assert row[0] is None
        assert row[1] is None
        assert row[2] is None


@pytest.mark.anyio
async def test_streaming_sends_done_when_upstream_does_not():
    """Proxy MUST send 'data: [DONE]' even when upstream omits it.

    Some providers (e.g. xiaomi/mimo) close the stream after the
    finish_reason chunk without sending [DONE]. The proxy must
    synthesize it so the client knows the stream is complete.
    """
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        config = _make_test_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        chunks = [
            {"choices": [{"delta": {"content": "Hello"}, "index": 0}]},
        ]
        mock_stream = _FakeStreamMethod(chunks, done=False)

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "openai/gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
                )
                lines = resp.text.strip().split("\n")
                last_line = lines[-1].strip()
                assert last_line == "data: [DONE]"

        telemetry.close()
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT response_body FROM requests").fetchone()
        conn.close()
        assert row is not None
        parsed = json.loads(row[0])
        assert parsed["streamed"] is True


# ------------------------------------------------------------------
# Streaming model name prefix regression (root cause of missing prefix)
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_streaming_model_name_prefix_in_db():
    """Streaming chunks WITH a 'model' field must produce a prefixed model_name in DB.

    Regression test for the bug where streaming telemetry stored NULL
    model_name because the upstream didn't include 'model' in chunks.
    When the upstream DOES include 'model', the stored model_name must
    be prefixed with the provider config name (e.g. 'openai/gpt-4').
    """
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "stream_model_prefix.sqlite"
        config = _make_test_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        chunks = [
            {"choices": [{"delta": {"content": "Hello"}, "index": 0}], "model": "gpt-4"},
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
                await resp.aread()

        telemetry.close()
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT model_name FROM requests").fetchone()
        conn.close()
        assert row is not None, "No telemetry record found"
        assert row[0] == "openai/gpt-4", (
            f"Expected prefixed model_name 'openai/gpt-4', got {row[0]!r}"
        )


@pytest.mark.anyio
async def test_streaming_anthropic_model_and_usage_from_nested_message():
    """Anthropic streaming chunks nest model/usage inside message_start.message.

    Regression test: model_name was NULL and early usage was missed because
    the code only checked top-level fields.  Anthropic SSE format puts them
    inside the 'message' object of message_start events.
    """
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "stream_anthropic.sqlite"
        config_path = Path(td) / "config.yaml"
        config_path.write_text(
            "providers:\n"
            "  - name: anthropic\n"
            "    base_url: https://api.anthropic.com\n"
            "    api_key: test-key\n"
            "    api_format: anthropic\n"
        )
        config = Config(config_path)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        # Anthropic SSE format: model and usage nested in message_start.message
        chunks = [
            {
                "type": "message_start",
                "message": {
                    "id": "msg_test123",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-4-20250514",
                    "content": [],
                    "usage": {"input_tokens": 42, "output_tokens": 0},
                },
            },
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Hello"},
            },
            {"type": "content_block_stop", "index": 0},
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 8},
            },
            {"type": "message_stop"},
        ]
        mock_stream = _FakeStreamMethod(chunks)

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/messages",
                    json={
                        "model": "anthropic/claude-sonnet-4-20250514",
                        "messages": [{"role": "user", "content": "hi"}],
                        "stream": True,
                    },
                )
                await resp.aread()

        telemetry.close()
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT model_name, input_tokens, output_tokens, total_tokens FROM requests"
        ).fetchone()
        conn.close()
        assert row is not None, "No telemetry record found"
        assert row[0] == "anthropic/claude-sonnet-4-20250514", (
            f"Expected prefixed model_name 'anthropic/claude-sonnet-4-20250514', got {row[0]!r}"
        )
        assert row[1] == 42, f"Expected input_tokens=42, got {row[1]}"
        assert row[2] == 8, f"Expected output_tokens=8, got {row[2]}"
        assert row[3] == 50, f"Expected total_tokens=50, got {row[3]}"


def test_v1_models_is_json_not_spa_html(tmp_path):
    """GET /v1/models must not be swallowed by the dashboard SPA fallback."""
    from fastapi.testclient import TestClient

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "providers:\n"
        "  - name: openai\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key: test-key\n"
        "    api_format: openai\n"
    )
    config = Config(config_path)
    telemetry = TelemetryLogger(tmp_path / "t.sqlite")
    app = create_app(config, telemetry)
    with TestClient(app) as client:
        models = client.get("/v1/models")
        assert models.headers["content-type"].startswith("application/json"), models.text[:200]
        body = models.json()
        assert body["object"] == "list"
        assert any(item.get("id") == "auto" for item in body["data"])

        health = client.get("/health")
        assert health.json() == {"status": "ok"}
    telemetry.close()


# ------------------------------------------------------------------
# Image generation endpoint tests
# ------------------------------------------------------------------


def test_image_generation_endpoint_exists():
    """POST /v1/images/generations route exists and accepts requests."""
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        config = _make_test_config(td)
        telemetry = TelemetryLogger(Path(td) / "t.sqlite")
        app = create_app(config, telemetry)
        with TestClient(app) as client:
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "created": 1234567890,
                    "data": [{"url": "https://example.com/image.png"}],
                }
                mock_resp.headers = {}
                mock_post.return_value = mock_resp

                resp = client.post(
                    "/v1/images/generations",
                    json={
                        "model": "openai/dall-e-3",
                        "prompt": "a cat",
                        "n": 1,
                        "size": "1024x1024",
                    },
                )
                assert resp.status_code == 200
                body = resp.json()
                assert "data" in body
                assert len(body["data"]) == 1
        telemetry.close()


def test_image_generation_anthropic_provider_returns_400():
    """Anthropic providers return 400 for image generation."""
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        config_path = Path(td) / "config.yaml"
        config_path.write_text(
            "providers:\n"
            "  - name: anthropic\n"
            "    base_url: https://api.anthropic.com\n"
            "    api_key: test-key\n"
            "    api_format: anthropic\n"
        )
        config = Config(config_path)
        telemetry = TelemetryLogger(Path(td) / "t.sqlite")
        app = create_app(config, telemetry)
        with TestClient(app) as client:
            resp = client.post(
                "/v1/images/generations",
                json={"model": "anthropic/claude-3", "prompt": "a cat"},
            )
            assert resp.status_code == 400
            body = resp.json()
            assert "error" in body
            assert "does not support image generation" in body["error"]["message"]
        telemetry.close()


def test_image_generation_invalid_model_format():
    """Invalid model format returns 400."""
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        config = _make_test_config(td)
        telemetry = TelemetryLogger(Path(td) / "t.sqlite")
        app = create_app(config, telemetry)
        with TestClient(app) as client:
            resp = client.post(
                "/v1/images/generations",
                json={"model": "no-slash", "prompt": "a cat"},
            )
            assert resp.status_code == 400
            body = resp.json()
            assert "error" in body
        telemetry.close()


def test_image_generation_unknown_provider():
    """Unknown provider returns 400."""
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        config = _make_test_config(td)
        telemetry = TelemetryLogger(Path(td) / "t.sqlite")
        app = create_app(config, telemetry)
        with TestClient(app) as client:
            resp = client.post(
                "/v1/images/generations",
                json={"model": "unknown/dall-e-3", "prompt": "a cat"},
            )
            assert resp.status_code == 400
            body = resp.json()
            assert "error" in body
        telemetry.close()


def test_image_generation_telemetry_logged():
    """Image generation request is logged to telemetry."""
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        config = _make_test_config(td)
        telemetry = TelemetryLogger(Path(td) / "t.sqlite")
        app = create_app(config, telemetry)
        with TestClient(app) as client:
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "created": 1234567890,
                    "data": [{"url": "https://example.com/image.png"}],
                    "model": "dall-e-3",
                }
                mock_resp.headers = {}
                mock_post.return_value = mock_resp

                resp = client.post(
                    "/v1/images/generations",
                    json={"model": "openai/dall-e-3", "prompt": "a cat"},
                )
                assert resp.status_code == 200

        telemetry.close()
        conn = sqlite3.connect(str(Path(td) / "t.sqlite"))
        row = conn.execute(
            "SELECT method, url, response_status, model_name FROM requests"
        ).fetchone()
        conn.close()
        assert row is not None, "No telemetry record found"
        assert row[0] == "POST"
        assert "/v1/images/generations" in row[1]
        assert row[2] == 200


# ------------------------------------------------------------------
# Image edit endpoint tests
# ------------------------------------------------------------------


def test_image_edit_endpoint_exists():
    """POST /v1/images/edits route exists and accepts multipart requests."""
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        config = _make_test_config(td)
        telemetry = TelemetryLogger(Path(td) / "t.sqlite")
        app = create_app(config, telemetry)
        with TestClient(app) as client:
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "created": 1234567890,
                    "data": [{"url": "https://example.com/edited.png"}],
                }
                mock_resp.headers = {}
                mock_post.return_value = mock_resp

                # Send multipart form with a fake image
                import io
                fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
                resp = client.post(
                    "/v1/images/edits",
                    files={"image": ("test.png", fake_image, "image/png")},
                    data={"prompt": "add a hat", "model": "openai/dall-e-2"},
                )
                assert resp.status_code == 200
                body = resp.json()
                assert "data" in body
        telemetry.close()


def test_image_edit_anthropic_provider_returns_400():
    """Anthropic providers return 400 for image editing."""
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        config_path = Path(td) / "config.yaml"
        config_path.write_text(
            "providers:\n"
            "  - name: anthropic\n"
            "    base_url: https://api.anthropic.com\n"
            "    api_key: test-key\n"
            "    api_format: anthropic\n"
        )
        config = Config(config_path)
        telemetry = TelemetryLogger(Path(td) / "t.sqlite")
        app = create_app(config, telemetry)
        with TestClient(app) as client:
            import io
            fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            resp = client.post(
                "/v1/images/edits",
                files={"image": ("test.png", fake_image, "image/png")},
                data={"prompt": "add a hat", "model": "anthropic/claude-3"},
            )
            assert resp.status_code == 400
            body = resp.json()
            assert "does not support image editing" in body["error"]["message"]
        telemetry.close()


# ------------------------------------------------------------------
# Model fallback from request body when upstream omits model
# ------------------------------------------------------------------

def test_non_streaming_model_falls_back_to_request_body():
    """When upstream response has no 'model' field, extract from request body.

    Regression test: model_name was NULL because _log_telemetry only read
    the model from the upstream response body, which some providers omit.
    """
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        config = _make_test_config(td)
        telemetry = TelemetryLogger(Path(td) / "t.sqlite")
        app = create_app(config, telemetry)
        with TestClient(app) as client:
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                # Upstream response has NO 'model' field
                mock_resp.json.return_value = {
                    "id": "chatcmpl-123",
                    "choices": [{"message": {"content": "hi"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                }
                mock_resp.headers = {}
                mock_post.return_value = mock_resp

                resp = client.post(
                    "/v1/chat/completions",
                    json={"model": "openai/gpt-4", "messages": [{"role": "user", "content": "hi"}]},
                )
                assert resp.status_code == 200

        telemetry.close()
        conn = sqlite3.connect(str(Path(td) / "t.sqlite"))
        row = conn.execute("SELECT model_name FROM requests").fetchone()
        conn.close()
        assert row is not None, "No telemetry record found"
        assert row[0] == "openai/gpt-4", (
            f"Expected 'openai/gpt-4' from request body fallback, got {row[0]!r}"
        )


@pytest.mark.anyio
async def test_streaming_model_falls_back_to_request_body():
    """When streaming chunks have no 'model' field, extract from request body.

    Regression test: streaming model_name was NULL because no chunk
    contained a 'model' field (some providers omit it from SSE chunks).
    """
    with tempfile.TemporaryDirectory() as td:
        config = _make_test_config(td)
        telemetry = TelemetryLogger(Path(td) / "t.sqlite")
        app = create_app(config, telemetry)

        # Chunks with NO 'model' field at all
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
                await resp.aread()

        telemetry.close()
        conn = sqlite3.connect(str(Path(td) / "t.sqlite"))
        row = conn.execute("SELECT model_name FROM requests").fetchone()
        conn.close()
        assert row is not None, "No telemetry record found"
        assert row[0] == "openai/gpt-4", (
            f"Expected 'openai/gpt-4' from request body fallback, got {row[0]!r}"
        )


# ------------------------------------------------------------------
# Streaming error response detection (non-SSE upstream errors)
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_streaming_surfaces_upstream_error_response():
    """When upstream returns a non-SSE error (e.g. 400 JSON) on a streaming
    endpoint, the proxy MUST surface the error to the client instead of
    yielding an empty stream.

    Regression test for: xAI returns 400 with JSON body for invalid model
    name, proxy yielded nothing, Claude Code saw empty stream.
    """
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        config = _make_test_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        error_body = {"code": "invalid-argument", "error": "Model not found: gpt-4[500k]"}
        mock_stream = _FakeErrorStreamMethod(400, error_body)

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"model": "openai/gpt-4[500k]", "messages": [{"role": "user", "content": "hi"}], "stream": True},
                )
                body = resp.text
                # The error must appear in the SSE stream, not be silently swallowed
                assert "Model not found" in body, (
                    f"Expected error message in stream output, got: {body[:500]}"
                )
                assert "data: [DONE]" in body, "Stream must end with [DONE]"

        telemetry.close()


@pytest.mark.anyio
async def test_anthropic_stream_from_openai_emits_message_start():
    """Claude Code on /v1/messages needs Anthropic SSE, not OpenAI content deltas."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        config = _make_test_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        chunks = [
            {
                "id": "chatcmpl-1",
                "model": "gpt-4",
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hi"}, "finish_reason": None}],
            },
            {
                "id": "chatcmpl-1",
                "model": "gpt-4",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
        ]
        mock_stream = _FakeStreamMethod(chunks)

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/messages",
                    json={
                        "model": "openai/gpt-4",
                        "max_tokens": 16,
                        "stream": True,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
                body = resp.text

        telemetry.close()
        assert "event: message_start" in body
        assert "event: content_block_delta" in body
        assert "event: message_stop" in body
        assert '"text": "Hi"' in body

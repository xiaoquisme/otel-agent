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
        assert not any(item.get("id") == "auto" for item in body["data"])

        health = client.get("/health")
        assert health.json() == {"status": "ok"}
    telemetry.close()


def test_bare_auto_model_is_invalid_on_chat_and_messages(tmp_path):
    """Bare model=auto is rejected like any unprefixed model."""
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
        chat = client.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
        )
        messages = client.post(
            "/v1/messages",
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
        )
    telemetry.close()
    assert chat.status_code == 400
    assert chat.json()["error"]["type"] == "invalid_request_error"
    assert "provider prefix" in chat.json()["error"]["message"]
    assert "X-Routed-Provider" not in chat.headers
    assert messages.status_code == 400
    assert messages.json()["error"]["type"] == "invalid_request_error"
    assert "X-Routed-Provider" not in messages.headers


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


# ------------------------------------------------------------------
# Vault-backed subscription credentials on the async request path (KTD1)
# ------------------------------------------------------------------
#
# Both of these exercise a bearer that comes from the vault rather than from
# provider.api_key, so they fail if a call site still resolves it synchronously
# (which would blow up with "coroutine was never awaited") or if resolution
# blocks the loop.


def _make_vault_config(td: str) -> Config:
    """A Config whose only provider is a subscription provider (no api_key)."""
    config_path = Path(td) / "config.yaml"
    config_path.write_text(
        "providers:\n"
        "  - name: codex\n"
        "    base_url: https://chatgpt.com/backend-api/codex\n"
        "    auth: codex-oauth\n"
        "    api_format: openai\n"
    )
    return Config(config_path)


def _seed_vault(tmp_path, monkeypatch) -> Path:
    from otel_agent.auth_vault import save_grant

    vault = tmp_path / "auth.json"
    save_grant(
        "codex",
        {"access_token": "tok-vault", "refresh_token": "ref-vault", "expires_in": 21600},
        auth="codex-oauth",
        discovery={"token_endpoint": "https://auth.openai.com/oauth/token"},
        path=vault,
    )
    # The client_id a refresh needs is recorded with the credential (U3 reads it
    # off the adopted grant); without it there is nothing to refresh with.
    stored = json.loads(vault.read_text())
    stored["providers"]["codex"]["client_id"] = "app_codex_test"
    vault.write_text(json.dumps(stored))
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(vault))
    return vault


class _RecordingStreamMethod:
    """Like _FakeStreamMethod, but records the headers the route sent upstream."""

    def __init__(self, chunks: list[dict], seen: dict):
        self._stream = _FakeSSEStream(chunks)
        self._seen = seen

    def __call__(self, *args, **kwargs):
        self._seen["headers"] = kwargs.get("headers")
        return self._stream


@pytest.mark.anyio
async def test_streaming_request_uses_the_vault_bearer(tmp_path, monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        _seed_vault(tmp_path, monkeypatch)
        config = _make_vault_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        seen: dict = {}
        mock_stream = _RecordingStreamMethod(
            [{"choices": [{"delta": {"content": "Hi"}, "index": 0}]}], seen
        )

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # The Responses route, not chat/completions: a Responses-only
                # provider is refused on the chat-shaped routes by design.
                resp = await client.post(
                    "/v1/responses",
                    json={"model": "codex/gpt-5", "input": "hi"},
                )
                await resp.aread()

        telemetry.close()

        assert seen["headers"]["Authorization"] == "Bearer tok-vault"


@pytest.mark.anyio
async def test_models_endpoint_uses_the_vault_bearer(tmp_path, monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        _seed_vault(tmp_path, monkeypatch)
        config = _make_vault_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        seen: dict = {}

        class _ModelsResponse:
            status_code = 200

            def json(self):
                return {"data": [{"id": "gpt-5", "object": "model"}]}

        real_get = httpx.AsyncClient.get

        async def _get(self, url, **kwargs):
            # Only the upstream model fetch is intercepted; the test client's own
            # GET of /v1/models must reach the app.
            if "chatgpt.com" in str(url):
                seen["url"] = url
                seen["headers"] = kwargs.get("headers")
                return _ModelsResponse()
            return await real_get(self, url, **kwargs)

        with patch("httpx.AsyncClient.get", _get):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/v1/models")

        telemetry.close()

        assert resp.status_code == 200
        assert seen["headers"] == {"Authorization": "Bearer tok-vault"}
        assert resp.json()["data"][0]["id"] == "codex/gpt-5"


@pytest.mark.anyio
async def test_bearer_resolution_does_not_block_the_event_loop(tmp_path, monkeypatch):
    """KTD1: a refresh runs off the loop. With resolution inlined on the loop,
    the heartbeat below could not tick while the exchange is in flight."""
    import asyncio
    import time as _time

    _seed_vault(tmp_path, monkeypatch)
    vault = tmp_path / "auth.json"
    stored = json.loads(vault.read_text())
    stored["providers"]["codex"]["tokens"]["expires_at"] = 0  # due for refresh
    vault.write_text(json.dumps(stored))

    class _RefreshResponse:
        status_code = 200

        def json(self):
            return {"access_token": "tok-new", "refresh_token": "ref-new", "expires_in": 21600}

    def _slow_post(*args, **kwargs):
        _time.sleep(0.3)
        return _RefreshResponse()

    monkeypatch.setattr("otel_agent.auth_vault.httpx.post", _slow_post)

    from otel_agent.config import Provider
    from otel_agent.provider_utils import resolve_bearer_async

    provider = Provider(
        name="codex",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="",
        auth="codex-oauth",
    )

    ticks = 0

    async def _heartbeat() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    beat = asyncio.create_task(_heartbeat())
    try:
        assert await resolve_bearer_async(provider) == "tok-new"
    finally:
        beat.cancel()

    assert ticks >= 3, f"the event loop was blocked during the refresh ({ticks} ticks)"


# ------------------------------------------------------------------
# U4: Responses passthrough route
# ------------------------------------------------------------------
#
# The subscription upstream serves only the Responses API, and only as a
# stream. This route is therefore a passthrough: no converter is installed,
# so the `event:` lines and blank separators of the upstream dialect survive
# to the client, and the normalization below is the whole of the gateway's
# vendor accommodation.


class _FakeLineStream:
    """SSE stub that yields a *line list* rather than a chunk-dict list.

    ``_FakeSSEStream`` cannot express this dialect: it hardcodes the
    ``data: `` prefix and appends ``[DONE]``, while a Responses stream's
    meaning lives in the ``event:`` lines.
    """

    def __init__(
        self,
        lines: list[str],
        *,
        status_code: int = 200,
        content_type: str = "text/event-stream",
        body: bytes = b"",
    ) -> None:
        self._lines = lines
        self._body = body
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def aread(self) -> bytes:
        return self._body

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _RecordingLineStreamMethod:
    """Sync mock for httpx.AsyncClient.stream() that records what was sent.

    ``stream()`` is a sync method returning an async context manager, so
    ``__call__`` must be sync (see ``_FakeStreamMethod``).
    """

    def __init__(self, stream: _FakeLineStream, seen: dict) -> None:
        self._stream = stream
        self._seen = seen

    def __call__(self, *args, **kwargs):
        if len(args) >= 2:
            self._seen["method"], self._seen["url"] = args[0], args[1]
        else:
            self._seen["method"] = kwargs.get("method")
            self._seen["url"] = kwargs.get("url")
        self._seen["headers"] = kwargs.get("headers")
        self._seen["json"] = kwargs.get("json")
        return self._stream


def _responses_lines(
    *, model: str = "gpt-5-codex", usage: dict | None = None, extra: dict | None = None,
) -> list[str]:
    """A plain-text Responses turn — the 9 event types the live probe saw.

    ``extra`` adds fields to the terminal envelope (``object``, ``output``, …)
    for callers that assert on the shape of the assembled response.
    """
    final_response: dict = {"id": "resp_1", "model": model, "status": "completed"}
    if usage is not None:
        final_response["usage"] = usage
    if extra is not None:
        final_response.update(extra)
    events: list[tuple[str, dict]] = [
        ("response.created", {"type": "response.created", "sequence_number": 0, "response": {"id": "resp_1", "model": model, "status": "in_progress"}}),
        ("response.in_progress", {"type": "response.in_progress", "sequence_number": 1, "response": {"id": "resp_1", "model": model, "status": "in_progress"}}),
        ("response.output_item.added", {"type": "response.output_item.added", "sequence_number": 2, "output_index": 0, "item": {"type": "message", "id": "msg_1", "status": "in_progress"}}),
        ("response.content_part.added", {"type": "response.content_part.added", "sequence_number": 3, "item_id": "msg_1", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": ""}}),
        ("response.output_text.delta", {"type": "response.output_text.delta", "sequence_number": 4, "item_id": "msg_1", "output_index": 0, "content_index": 0, "delta": "Hello"}),
        ("response.output_text.done", {"type": "response.output_text.done", "sequence_number": 5, "item_id": "msg_1", "output_index": 0, "content_index": 0, "text": "Hello"}),
        ("response.content_part.done", {"type": "response.content_part.done", "sequence_number": 6, "item_id": "msg_1", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "Hello"}}),
        ("response.output_item.done", {"type": "response.output_item.done", "sequence_number": 7, "output_index": 0, "item": {"type": "message", "id": "msg_1", "status": "completed"}}),
        ("response.completed", {"type": "response.completed", "sequence_number": 8, "response": final_response}),
    ]
    lines: list[str] = []
    for name, payload in events:
        lines.append(f"event: {name}")
        lines.append(f"data: {json.dumps(payload)}")
        lines.append("")
    return lines


def _nonempty_lines(body: str) -> list[str]:
    return [line for line in body.split("\n") if line.strip()]


@pytest.mark.anyio
async def test_responses_route_normalizes_request_without_rewriting_semantics(tmp_path, monkeypatch):
    """Passthrough + normalization: the client's input survives, the vendor
    accommodation is applied, and nothing else about the body is touched."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        _seed_vault(tmp_path, monkeypatch)
        config = _make_vault_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        seen: dict = {}
        mock_stream = _RecordingLineStreamMethod(_FakeLineStream(_responses_lines()), seen)

        sent_input = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}]
        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/responses",
                    json={
                        "model": "codex/gpt-5-codex",
                        "input": sent_input,
                        "stream": False,
                        "store": True,
                        "include": ["message.output_text.logprobs"],
                        "max_output_tokens": 64,
                        "temperature": 0.5,
                        "instructions": "be brief",
                    },
                )
                await resp.aread()
                health = await client.get("/health")

        telemetry.close()

        assert seen["method"] == "POST"
        assert seen["url"] == "https://chatgpt.com/backend-api/codex/responses", seen["url"]
        forwarded = seen["json"]

        # Normalization: stream forced, store/include overridden whatever the
        # client asked for, and the two parameters this upstream rejects gone.
        assert forwarded["stream"] is True
        assert forwarded["store"] is False
        assert forwarded["include"] == ["reasoning.encrypted_content"]
        assert "max_output_tokens" not in forwarded
        assert "temperature" not in forwarded

        # No rewrite of semantics: everything else is verbatim.
        assert forwarded["input"] == sent_input
        assert forwarded["instructions"] == "be brief"
        assert forwarded["model"] == "gpt-5-codex"

        # No identity headers ride along with the subscription bearer.
        assert set(seen["headers"]) == {"Authorization", "Content-Type"}

        # Regression: the new route must not disturb the JSON endpoints.
        assert health.headers["content-type"].startswith("application/json")
        assert health.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_responses_route_preserves_event_lines_and_blank_separators(tmp_path, monkeypatch):
    """Event fidelity: `event:` lines and their blank separators reach the client."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        _seed_vault(tmp_path, monkeypatch)
        config = _make_vault_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        upstream_lines = _responses_lines()
        mock_stream = _RecordingLineStreamMethod(_FakeLineStream(upstream_lines), {})

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/responses",
                    json={"model": "codex/gpt-5-codex", "input": "hi", "stream": True},
                )
                body = resp.text

        telemetry.close()

        # Every upstream line that carries meaning survives, in order. `data:`
        # lines are re-serialized (JSON, so equivalent); `event:` lines are
        # byte-identical.
        upstream_nonempty = [line for line in upstream_lines if line.strip()]
        assert _nonempty_lines(body) == upstream_nonempty, body[:800]

        # Each event is delivered: an `event: <name>` line, its `data:` line,
        # and a blank separator.
        for name in (
            "response.created",
            "response.in_progress",
            "response.output_item.added",
            "response.content_part.added",
            "response.output_text.delta",
            "response.output_text.done",
            "response.content_part.done",
            "response.output_item.done",
            "response.completed",
        ):
            assert f"event: {name}\n" in body, f"missing event line for {name}"

        assert "\n\n" in body, "blank separators were dropped"
        delta = json.loads(body.split("event: response.output_text.delta\n")[1].split("data: ", 1)[1].split("\n", 1)[0])
        assert delta["delta"] == "Hello"
        assert delta["type"] == "response.output_text.delta"


@pytest.mark.anyio
async def test_responses_route_does_not_synthesize_done(tmp_path, monkeypatch):
    """A Responses stream ends at `response.completed` — no `[DONE]` sentinel."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        _seed_vault(tmp_path, monkeypatch)
        config = _make_vault_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        mock_stream = _RecordingLineStreamMethod(_FakeLineStream(_responses_lines()), {})

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/responses",
                    json={"model": "codex/gpt-5-codex", "input": "hi", "stream": True},
                )
                body = resp.text

        telemetry.close()

        assert "[DONE]" not in body, "a [DONE] sentinel was synthesized for a Responses client"
        assert _nonempty_lines(body)[-2] == "event: response.completed"


@pytest.mark.anyio
async def test_responses_route_upstream_rejection_becomes_an_error_event(tmp_path, monkeypatch):
    """R12: an upstream refusal must reach a Responses client as a parseable
    error event, not as a bare data frame or a dead stream."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        _seed_vault(tmp_path, monkeypatch)
        config = _make_vault_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        # The shape the live upstream uses for a rejected parameter.
        upstream_body = json.dumps({"detail": "Unsupported parameter: temperature"}).encode()
        mock_stream = _RecordingLineStreamMethod(
            _FakeLineStream([], status_code=400, content_type="application/json", body=upstream_body),
            {},
        )

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/responses",
                    json={"model": "codex/gpt-5-codex", "input": "hi", "stream": True},
                )
                body = resp.text

        telemetry.close()

        assert body.startswith("event: error\n"), body[:400]
        assert "data: [DONE]" not in body, "a Responses client must not be handed a chat sentinel"
        payload = json.loads(body.split("data: ", 1)[1])
        assert payload["type"] == "error"
        assert "Unsupported parameter: temperature" in payload["message"]


@pytest.mark.anyio
async def test_responses_telemetry_uses_responses_usage_and_model(tmp_path, monkeypatch):
    """KTD7: usage and model live inside the `response` object, not at the
    top level, so the chat-shaped extraction logs nothing for this stream."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        _seed_vault(tmp_path, monkeypatch)
        config = _make_vault_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        lines = _responses_lines(
            usage={"input_tokens": 1200, "output_tokens": 40, "total_tokens": 1240}
        )
        mock_stream = _RecordingLineStreamMethod(_FakeLineStream(lines), {})

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/responses",
                    json={"model": "codex/gpt-5-codex", "input": "hi", "stream": True},
                )
                await resp.aread()

        telemetry.close()

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT model_name, input_tokens, output_tokens, total_tokens, format FROM requests"
        ).fetchone()
        conn.close()

        assert row is not None, "No telemetry record found"
        assert row[0] == "codex/gpt-5-codex", f"Expected the Responses model name, got {row[0]!r}"
        assert row[1] == 1200
        assert row[2] == 40
        assert row[3] == 1240
        assert row[4] == "responses", f"Expected format 'responses', got {row[4]!r}"


class _FailingStreamMethod:
    """Mock for httpx.AsyncClient.stream() that fails before any stream opens."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __call__(self, *args, **kwargs):
        raise self._exc


@pytest.mark.anyio
async def test_responses_route_connection_failure_is_an_error_event(tmp_path, monkeypatch):
    """R12's other half: a failure before the upstream answers is still a
    Responses-shaped error event, not a bare frame or a dead stream."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        _seed_vault(tmp_path, monkeypatch)
        config = _make_vault_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        with patch("httpx.AsyncClient.stream", _FailingStreamMethod(httpx.ConnectError("boom"))):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/responses",
                    json={"model": "codex/gpt-5-codex", "input": "hi", "stream": True},
                )
                body = resp.text

        telemetry.close()

        assert body.startswith("event: error\n"), body[:400]
        payload = json.loads(body.split("data: ", 1)[1])
        assert payload["type"] == "error"
        assert "Connection failed" in payload["message"]
        assert "boom" in payload["message"]


@pytest.mark.anyio
async def test_responses_route_passes_unknown_event_types_untouched(tmp_path, monkeypatch):
    """Tool-call event shapes were never probed, so the route must not depend
    on knowing the event vocabulary: an event it has never seen passes
    through verbatim."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        _seed_vault(tmp_path, monkeypatch)
        config = _make_vault_config(td)
        telemetry = TelemetryLogger(db_path)
        app = create_app(config, telemetry)

        tool_lines = [
            "event: response.function_call_arguments.delta",
            'data: {"type": "response.function_call_arguments.delta", "sequence_number": 9, "item_id": "fc_1", "output_index": 0, "delta": "{\\"city\\":\\"SF\\"}"}',
            "",
            "event: response.function_call_arguments.done",
            'data: {"type": "response.function_call_arguments.done", "sequence_number": 10, "item_id": "fc_1", "output_index": 0, "arguments": "{\\"city\\":\\"SF\\"}"}',
            "",
        ]
        mock_stream = _RecordingLineStreamMethod(
            _FakeLineStream(_responses_lines() + tool_lines), {}
        )

        with patch("httpx.AsyncClient.stream", mock_stream):
            from httpx import ASGITransport
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/responses",
                    json={"model": "codex/gpt-5-codex", "input": "weather in SF?", "stream": True},
                )
                body = resp.text

        telemetry.close()

        for line in tool_lines:
            if line.strip():
                assert line in body, f"upstream line was altered or dropped: {line!r}"


def test_chat_shaped_routes_refuse_a_responses_only_provider(tmp_path):
    """The subscription upstream serves only the Responses surface, so the
    chat-shaped routes refuse it by declaration instead of forwarding."""
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        config = _make_vault_config(td)
        telemetry = TelemetryLogger(Path(td) / "t.sqlite")
        app = create_app(config, telemetry)
        with TestClient(app) as client:
            with patch("httpx.AsyncClient.stream") as stream, patch("httpx.AsyncClient.post") as post:
                chat = client.post(
                    "/v1/chat/completions",
                    json={"model": "codex/gpt-5-codex", "messages": [{"role": "user", "content": "hi"}]},
                )
                messages = client.post(
                    "/v1/messages",
                    json={"model": "codex/gpt-5-codex", "messages": [{"role": "user", "content": "hi"}]},
                )
        telemetry.close()

    for resp, endpoint in ((chat, "/v1/chat/completions"), (messages, "/v1/messages")):
        assert resp.status_code == 400, f"{endpoint} forwarded instead of refusing"
        body = resp.json()
        assert body["error"]["type"] == "invalid_request_error"
        assert "codex" in body["error"]["message"]
        assert "Responses" in body["error"]["message"], body["error"]["message"]
        assert "/v1/responses" in body["error"]["message"], body["error"]["message"]
    assert not stream.called, "a chat-shaped refusal must not reach the upstream"
    assert not post.called, "a chat-shaped refusal must not reach the upstream"


def test_responses_route_declines_providers_without_a_responses_surface(tmp_path):
    """The route's normalization is this upstream's accommodation, so it is
    only served for a provider that declares a Responses surface."""
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        config = _make_test_config(td)
        telemetry = TelemetryLogger(Path(td) / "t.sqlite")
        app = create_app(config, telemetry)
        with TestClient(app) as client:
            with patch("httpx.AsyncClient.stream") as stream:
                resp = client.post(
                    "/v1/responses",
                    json={"model": "openai/gpt-5", "input": "hi"},
                )
        telemetry.close()

    assert resp.status_code == 400
    assert resp.json()["error"]["type"] == "invalid_request_error"
    assert "openai" in resp.json()["error"]["message"]
    assert not stream.called


def test_responses_previous_response_id_is_rejected_as_stateless(tmp_path):
    """R8: continuation is deliberately unsupported. Stripping the parameter
    would hand a state-dependent client a successful, contextless answer, so
    it is refused distinguishably instead."""
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        config = _make_vault_config(td)
        telemetry = TelemetryLogger(Path(td) / "t.sqlite")
        app = create_app(config, telemetry)
        with TestClient(app) as client:
            with patch("httpx.AsyncClient.stream") as stream:
                resp = client.post(
                    "/v1/responses",
                    json={"model": "codex/gpt-5-codex", "input": "and then?", "previous_response_id": "resp_abc"},
                )
        telemetry.close()

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["type"] == "invalid_request_error"
    assert "previous_response_id" in body["error"]["message"]
    assert "stateless" in body["error"]["message"].lower()
    assert "input" in body["error"]["message"]
    assert not stream.called, "the parameter must be refused, not forwarded"


# ------------------------------------------------------------------
# U5: aggregation for a non-streaming Responses client
# ------------------------------------------------------------------
#
# The upstream serves this dialect as a stream and nothing else. A client that
# asks for a single response is served by asking upstream in the only form it
# accepts and folding the stream back into the one object the client asked for.
# KTD5: this is its own handler, not `_handle_non_streaming` — the latter posts
# once and would forward the upstream's `{"detail": "Stream must be set to
# true"}` straight back to the client.


class _StreamOnlyLineStreamMethod:
    """A line-stream mock that models the real upstream's one hard rule.

    A request that does not set ``stream: true`` gets the same 400 the live
    upstream returns, so a gateway that ever stopped asking in streaming form
    fails these tests instead of quietly degrading.
    """

    def __init__(self, lines: list[str], seen: dict | None = None) -> None:
        self._lines = lines
        self.seen: dict = seen if seen is not None else {}

    def __call__(self, *args, **kwargs):
        body = kwargs.get("json") or {}
        self.seen["json"] = body
        self.seen["url"] = args[1] if len(args) >= 2 else kwargs.get("url")
        self.seen["headers"] = kwargs.get("headers")
        if body.get("stream") is not True:
            return _FakeLineStream(
                [],
                status_code=400,
                content_type="application/json",
                body=json.dumps({"detail": "Stream must be set to true"}).encode(),
            )
        return _FakeLineStream(self._lines)


def _prose_envelope() -> dict:
    """The terminal envelope of a plain-text turn, as the live probe saw it."""
    return {
        "object": "response",
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "status": "completed",
                "content": [{"type": "output_text", "text": "Hello"}],
            }
        ],
    }


def _terminal_envelope(lines: list[str]) -> dict:
    """The `response` object carried by the fixture's `response.completed`."""
    idx = lines.index("event: response.completed")
    return json.loads(lines[idx + 1][len("data: "):])["response"]


def _responses_app(td: str, tmp_path, monkeypatch):
    _seed_vault(tmp_path, monkeypatch)
    config = _make_vault_config(td)
    telemetry = TelemetryLogger(Path(td) / "test.sqlite")
    return create_app(config, telemetry), telemetry


async def _post_responses(app, payload: dict):
    from httpx import ASGITransport
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/responses", json=payload)
        await resp.aread()
        return resp


@pytest.mark.anyio
async def test_responses_non_streaming_request_is_aggregated_from_the_upstream_stream(tmp_path, monkeypatch):
    """AE1/R9: the client asks for one response and never learns that the
    upstream only streams — the gateway asks in streaming form and hands back
    the single object the client asked for."""
    with tempfile.TemporaryDirectory() as td:
        app, telemetry = _responses_app(td, tmp_path, monkeypatch)

        usage = {"input_tokens": 12, "output_tokens": 1, "total_tokens": 13}
        lines = _responses_lines(usage=usage, extra=_prose_envelope())
        mock_stream = _StreamOnlyLineStreamMethod(lines)

        with patch("httpx.AsyncClient.stream", mock_stream):
            resp = await _post_responses(
                app, {"model": "codex/gpt-5-codex", "input": "hi", "stream": False}
            )

        telemetry.close()

        # AE1's Given, negated: the gateway asked in the only form the upstream
        # accepts, so the upstream's "Stream must be set to true" 400 never
        # happens and the client's own `stream: false` is not forwarded.
        assert mock_stream.seen["json"]["stream"] is True
        assert mock_stream.seen["url"] == "https://chatgpt.com/backend-api/codex/responses"

        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/json"), resp.headers["content-type"]

        # The aggregated body is the envelope the upstream itself sent in the
        # terminal event — taken, not reconstructed.
        assert resp.json() == _terminal_envelope(lines)


@pytest.mark.anyio
async def test_responses_aggregated_body_has_the_responses_dialect_shape(tmp_path, monkeypatch):
    """R9: what comes back is a Responses response object, not a chat body and
    not a wrapper around the event stream."""
    with tempfile.TemporaryDirectory() as td:
        app, telemetry = _responses_app(td, tmp_path, monkeypatch)

        usage = {"input_tokens": 12, "output_tokens": 1, "total_tokens": 13}
        lines = _responses_lines(usage=usage, extra=_prose_envelope())

        with patch("httpx.AsyncClient.stream", _StreamOnlyLineStreamMethod(lines)):
            resp = await _post_responses(
                app, {"model": "codex/gpt-5-codex", "input": "hi", "stream": False}
            )

        telemetry.close()

        body = resp.json()
        assert body["object"] == "response"
        assert body["id"] == "resp_1"
        assert body["model"] == "gpt-5-codex"
        assert body["status"] == "completed"
        assert body["usage"] == usage
        assert body["output"][0]["content"][0]["text"] == "Hello"

        # The client's dialect has no `choices`, and nothing was wrapped around
        # the response object to carry the events that produced it.
        assert "choices" not in body
        assert "events" not in body
        assert "streamed" not in body


@pytest.mark.anyio
async def test_responses_aggregated_stream_that_ends_early_is_a_diagnosable_error(tmp_path, monkeypatch):
    """R9: a stream that dies mid-answer must not reach a non-streaming client
    as an empty 200 — there is no `event: error` frame for it to read."""
    with tempfile.TemporaryDirectory() as td:
        app, telemetry = _responses_app(td, tmp_path, monkeypatch)

        # Every event but the terminal one: the upstream stopped mid-turn.
        truncated = _responses_lines()[:-3]
        with patch("httpx.AsyncClient.stream", _StreamOnlyLineStreamMethod(truncated)):
            resp = await _post_responses(
                app, {"model": "codex/gpt-5-codex", "input": "hi", "stream": False}
            )

        telemetry.close()

        assert resp.status_code >= 400, resp.text
        body = resp.json()
        assert body["error"]["message"], "the client was handed an empty error"
        assert "response.completed" in body["error"]["message"]
        assert "codex" in body["error"]["message"]


@pytest.mark.anyio
async def test_responses_aggregated_mid_stream_error_event_is_a_diagnosable_error(tmp_path, monkeypatch):
    """R9: an error raised after the stream opened is reported as an error, not
    discarded in favour of the partial answer that preceded it."""
    with tempfile.TemporaryDirectory() as td:
        app, telemetry = _responses_app(td, tmp_path, monkeypatch)

        error_frame = [
            "event: error",
            'data: {"type": "error", "code": null, "message": "upstream gave up mid-answer", "param": null, "sequence_number": 4}',
            "",
        ]
        with patch("httpx.AsyncClient.stream", _StreamOnlyLineStreamMethod(_responses_lines()[:6] + error_frame)):
            resp = await _post_responses(
                app, {"model": "codex/gpt-5-codex", "input": "hi", "stream": False}
            )

        telemetry.close()

        assert resp.status_code >= 400, resp.text
        assert "upstream gave up mid-answer" in resp.json()["error"]["message"]


@pytest.mark.anyio
async def test_responses_aggregated_upstream_rejection_keeps_its_status_and_reason(tmp_path, monkeypatch):
    """R9: a rejection the upstream never turned into a stream reaches the
    client as a non-2xx carrying the upstream's own reason."""
    with tempfile.TemporaryDirectory() as td:
        app, telemetry = _responses_app(td, tmp_path, monkeypatch)

        mock_stream = _RecordingLineStreamMethod(
            _FakeLineStream(
                [],
                status_code=400,
                content_type="application/json",
                body=json.dumps({"detail": "Unsupported parameter: temperature"}).encode(),
            ),
            {},
        )
        with patch("httpx.AsyncClient.stream", mock_stream):
            resp = await _post_responses(
                app, {"model": "codex/gpt-5-codex", "input": "hi", "stream": False}
            )

        telemetry.close()

        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body["error"]["message"]
        assert "Unsupported parameter: temperature" in body["error"]["message"]
        assert body["error"]["type"] == "invalid_request_error"


@pytest.mark.anyio
async def test_responses_aggregated_connection_failure_is_not_an_empty_200(tmp_path, monkeypatch):
    """R9: failing before the upstream answers is a gateway-level error."""
    with tempfile.TemporaryDirectory() as td:
        app, telemetry = _responses_app(td, tmp_path, monkeypatch)

        with patch("httpx.AsyncClient.stream", _FailingStreamMethod(httpx.ConnectError("boom"))):
            resp = await _post_responses(
                app, {"model": "codex/gpt-5-codex", "input": "hi", "stream": False}
            )

        telemetry.close()

        assert resp.status_code == 502, resp.text
        body = resp.json()
        assert "Connection failed" in body["error"]["message"]
        assert "boom" in body["error"]["message"]


@pytest.mark.anyio
async def test_responses_aggregated_request_is_logged(tmp_path, monkeypatch):
    """The dashboard sees the same request a streaming client produces: the
    aggregated answer, its usage, and the Responses format."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite"
        app, telemetry = _responses_app(td, tmp_path, monkeypatch)

        usage = {"input_tokens": 12, "output_tokens": 1, "total_tokens": 13}
        lines = _responses_lines(usage=usage, extra=_prose_envelope())

        with patch("httpx.AsyncClient.stream", _StreamOnlyLineStreamMethod(lines)):
            resp = await _post_responses(
                app, {"model": "codex/gpt-5-codex", "input": "hi", "stream": False}
            )

        telemetry.close()
        assert resp.status_code == 200, resp.text

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT model_name, input_tokens, output_tokens, total_tokens, format, response_body FROM requests"
        ).fetchone()
        conn.close()

        assert row is not None, "the aggregated request was not logged"
        assert row[0] == "codex/gpt-5-codex"
        assert (row[1], row[2], row[3]) == (12, 1, 13)
        assert row[4] == "responses"
        logged = json.loads(row[5])
        assert logged.get("streamed") is not True
        assert logged["output"][0]["content"][0]["text"] == "Hello"


@pytest.mark.anyio
async def test_responses_streaming_client_still_gets_a_stream(tmp_path, monkeypatch):
    """Streaming is this gateway's default form, so a client that asks for it —
    or says nothing — is not aggregated."""
    with tempfile.TemporaryDirectory() as td:
        app, telemetry = _responses_app(td, tmp_path, monkeypatch)

        lines = _responses_lines()
        mock_stream = _StreamOnlyLineStreamMethod(lines)

        with patch("httpx.AsyncClient.stream", mock_stream):
            resp = await _post_responses(
                app, {"model": "codex/gpt-5-codex", "input": "hi", "stream": True}
            )

        telemetry.close()

        assert resp.headers["content-type"].startswith("text/event-stream"), resp.headers["content-type"]
        assert "event: response.completed" in resp.text


# ------------------------------------------------------------------
# U6: a credential failure is its own class of error, and it is one
# provider's alone (R11 / R12 / KTD6 / KTD8)
# ------------------------------------------------------------------


def _make_mixed_config(td: str) -> Config:
    """One plain provider beside the subscription provider."""
    config_path = Path(td) / "config.yaml"
    config_path.write_text(
        "providers:\n"
        "  - name: openai\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key: sk-plain\n"
        "    api_format: openai\n"
        "  - name: codex\n"
        "    base_url: https://chatgpt.com/backend-api/codex\n"
        "    auth: codex-oauth\n"
        "    api_format: openai\n"
    )
    return Config(config_path)


class _ModelsResponse:
    status_code = 200

    def json(self):
        return {"data": [{"id": "gpt-4o", "object": "model"}]}


class _CliResult:
    """What subprocess.run hands back, without a subprocess."""

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = ""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def _patch_models_get(monkeypatch, seen: dict) -> None:
    """Serve the plain provider's model list, and never let a call reach a
    provider whose credential the gateway does not have."""
    real_get = httpx.AsyncClient.get

    async def _get(self, url, **kwargs):
        url = str(url)
        if "chatgpt.com" in url:
            raise AssertionError(f"a credential-less provider was called upstream: {url}")
        if "api.openai.com" not in url:
            # The test client's own GET of /v1/models must reach the app.
            return await real_get(self, url, **kwargs)
        seen["url"] = url
        return _ModelsResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", _get)


async def _get_models(app, **params):
    from httpx import ASGITransport
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/v1/models", params=params or None)


@pytest.mark.anyio
async def test_models_route_localizes_a_credential_failure_to_its_provider(tmp_path, monkeypatch):
    """KTD6/AE2: the broken provider is named rather than silently absent, and
    the providers that are fine still answer."""
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(tmp_path / "absent.json"))
    with tempfile.TemporaryDirectory() as td:
        telemetry = TelemetryLogger(Path(td) / "test.sqlite")
        app = create_app(_make_mixed_config(td), telemetry)
        seen: dict = {}
        _patch_models_get(monkeypatch, seen)

        resp = await _get_models(app)
        telemetry.close()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [m["id"] for m in body["data"]] == ["openai/gpt-4o"]
    assert [e["provider"] for e in body["errors"]] == ["codex"]
    assert "vault" in body["errors"][0]["message"]
    assert body["errors"][0]["type"] == "credential_error"
    # The broken provider is the only one that was not asked upstream.
    assert seen["url"] == "https://api.openai.com/v1/models"


@pytest.mark.anyio
async def test_models_route_for_a_broken_provider_is_an_explicit_error(tmp_path, monkeypatch):
    """specs/009-models-api allows a clear error: a client that asked for
    exactly that provider must not read the answer as "it has no models"."""
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(tmp_path / "absent.json"))
    with tempfile.TemporaryDirectory() as td:
        telemetry = TelemetryLogger(Path(td) / "test.sqlite")
        app = create_app(_make_mixed_config(td), telemetry)
        seen: dict = {}
        _patch_models_get(monkeypatch, seen)

        resp = await _get_models(app, provider="codex")
        telemetry.close()

    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["type"] == "credential_error"
    assert "codex" in resp.json()["error"]["message"]
    assert seen == {}


@pytest.mark.anyio
async def test_models_route_lists_declared_models_without_a_credential(tmp_path, monkeypatch):
    """A provider that declares its models is listed from the declaration: the
    upstream is never called, and a broken credential is not an error here
    because no credential was needed to answer."""
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(tmp_path / "absent.json"))
    with tempfile.TemporaryDirectory() as td:
        config_path = Path(td) / "config.yaml"
        config_path.write_text(
            "providers:\n"
            "  - name: openai\n"
            "    base_url: https://api.openai.com/v1\n"
            "    api_key: sk-plain\n"
            "    api_format: openai\n"
            "  - name: codex\n"
            "    base_url: https://chatgpt.com/backend-api/codex\n"
            "    auth: codex-oauth\n"
            "    api_format: openai\n"
            "    models:\n"
            "      - gpt-5.6-sol\n"
        )
        telemetry = TelemetryLogger(Path(td) / "test.sqlite")
        app = create_app(Config(config_path), telemetry)
        seen: dict = {}
        # _patch_models_get fails the test on any call to chatgpt.com.
        _patch_models_get(monkeypatch, seen)

        resp = await _get_models(app)
        telemetry.close()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [m["id"] for m in body["data"]] == ["codex/gpt-5.6-sol", "openai/gpt-4o"]
    assert "errors" not in body
    assert seen["url"] == "https://api.openai.com/v1/models"


@pytest.mark.anyio
async def test_models_route_lists_cli_sourced_models_without_a_credential(tmp_path, monkeypatch):
    """A provider whose catalog is declared as coming from the vendor CLI is
    listed from that CLI: the subscription endpoint (which publishes nothing)
    is never called, and the id a client sees is prefixed like any other."""
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(tmp_path / "absent.json"))
    catalog = json.dumps({"models": [
        {"slug": "gpt-6-astra", "visibility": "list"},
        {"slug": "gpt-5.6-sol", "visibility": "list"},
    ]})
    calls: list[list[str]] = []
    # Stubbed: no test may run the real `codex` binary.
    monkeypatch.setattr("otel_agent.cli_models.shutil.which", lambda name: "/usr/local/bin/codex")
    monkeypatch.setattr(
        "otel_agent.cli_models.subprocess.run",
        lambda argv, **kwargs: calls.append(list(argv)) or _CliResult(catalog),
    )
    with tempfile.TemporaryDirectory() as td:
        config_path = Path(td) / "config.yaml"
        config_path.write_text(
            "providers:\n"
            "  - name: openai\n"
            "    base_url: https://api.openai.com/v1\n"
            "    api_key: sk-plain\n"
            "    api_format: openai\n"
            "  - name: codex\n"
            "    base_url: https://chatgpt.com/backend-api/codex\n"
            "    auth: codex-oauth\n"
            "    api_format: openai\n"
            "    models_from: codex-cli\n"
        )
        telemetry = TelemetryLogger(Path(td) / "test.sqlite")
        app = create_app(Config(config_path), telemetry)
        seen: dict = {}
        # _patch_models_get fails the test on any call to chatgpt.com.
        _patch_models_get(monkeypatch, seen)

        resp = await _get_models(app)
        telemetry.close()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [m["id"] for m in body["data"]] == [
        "codex/gpt-6-astra", "codex/gpt-5.6-sol", "openai/gpt-4o",
    ]
    assert "errors" not in body
    assert seen["url"] == "https://api.openai.com/v1/models"
    assert calls == [["/usr/local/bin/codex", "debug", "models"]]


@pytest.mark.anyio
async def test_a_subscription_request_without_a_grant_is_diagnosable(tmp_path, monkeypatch):
    """R12/AE2: a credential failure arrives as its own class of error,
    carrying the subscription's current status — not as an unclassified 500."""
    monkeypatch.setenv("OTEL_AGENT_AUTH_PATH", str(tmp_path / "absent.json"))
    with tempfile.TemporaryDirectory() as td:
        telemetry = TelemetryLogger(Path(td) / "test.sqlite")
        app = create_app(_make_vault_config(td), telemetry)

        from httpx import ASGITransport
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/responses", json={"model": "codex/gpt-5", "input": "hi"})
        telemetry.close()

    assert resp.status_code != 500, resp.text
    body = resp.json()
    assert body["error"]["type"] == "credential_error"
    assert body["error"]["code"] == "credential_unavailable"
    assert body["error"]["provider"] == "codex"
    assert "vault" in body["error"]["message"]
    # AE2: the error carries the current status, not just a complaint.
    assert body["credential"]["available"] is False
    assert body["credential"]["last_result"] is None


@pytest.mark.anyio
async def test_an_unrefreshable_grant_is_a_credential_error(tmp_path, monkeypatch):
    """AE2's Given in full: the grant is present, expired, and cannot be
    refreshed. The client is told the credential is the problem, and nothing is
    sent upstream bearing a token that is known to be dead."""
    with tempfile.TemporaryDirectory() as td:
        _seed_vault(tmp_path, monkeypatch)
        vault = tmp_path / "auth.json"
        stored = json.loads(vault.read_text())
        stored["providers"]["codex"]["tokens"]["expires_at"] = 0
        vault.write_text(json.dumps(stored))

        telemetry = TelemetryLogger(Path(td) / "test.sqlite")
        app = create_app(_make_vault_config(td), telemetry)

        class _Rejected:
            status_code = 401

            def json(self):
                return {"error": "invalid_grant"}

        monkeypatch.setattr("otel_agent.auth_vault.httpx.post", lambda *a, **k: _Rejected())

        def _no_stream(*args, **kwargs):
            raise AssertionError("the upstream was called with a credential known to be dead")

        from httpx import ASGITransport
        with patch("httpx.AsyncClient.stream", _no_stream):
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/v1/responses", json={"model": "codex/gpt-5", "input": "hi"})
        telemetry.close()

    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body["error"]["type"] == "credential_error"
    assert "401" in body["error"]["message"]
    # The failed refresh is on record, so the operator sees why (R11).
    assert body["credential"]["last_result"]["ok"] is False

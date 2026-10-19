"""Session correlation: headers, storage migration, and trajectory APIs."""
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from otel_agent.config import Config
from otel_agent.dashboard.api import DashboardAPI
from otel_agent.dashboard.routes import router as dashboard_router
from otel_agent.dashboard.routes import set_api as set_dashboard_api
from otel_agent.logger import TelemetryLogger
from otel_agent.server import _log_telemetry, create_app
from otel_agent.sessions import (
    SLOW_STEP_MS,
    assemble_session,
    session_fields_from_headers,
    step_flags,
)
from otel_agent.viewer import format_session_detail, format_session_summary, query_session


def _legacy_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            method TEXT NOT NULL,
            url TEXT NOT NULL,
            upstream TEXT,
            request_headers TEXT,
            request_body TEXT,
            response_status INTEGER,
            response_headers TEXT,
            response_body TEXT,
            latency_ms REAL
        )
        """
    )
    conn.execute(
        "INSERT INTO requests (timestamp, method, url, response_status, latency_ms) "
        "VALUES ('2026-01-01T00:00:00+00:00', 'POST', 'http://old.example/v1/chat/completions', 200, 12.0)"
    )
    conn.commit()
    conn.close()


def _log(logger: TelemetryLogger, **overrides) -> None:
    payload = dict(
        method="POST",
        url="http://localhost:45638/v1/chat/completions",
        request_headers={},
        request_body='{"model":"openai/gpt-4o","messages":[{"role":"user","content":"hi"}]}',
        response_status=200,
        response_headers={},
        response_body="{}",
        latency_ms=100.0,
        upstream="https://api.openai.com/v1",
        model_name="openai/gpt-4o",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        timestamp="2026-04-01T00:00:00+00:00",
    )
    payload.update(overrides)
    logger.log_request(**payload)


def _make_request(headers: dict | None = None) -> MagicMock:
    request = MagicMock()
    request.method = "POST"
    request.url = "http://localhost:45638/v1/chat/completions"
    request.headers = headers or {"content-type": "application/json"}
    return request


def _make_provider() -> MagicMock:
    provider = MagicMock()
    provider.name = "openai"
    provider.base_url = "https://api.openai.com/v1"
    return provider


def _client(db_path: Path):
    app = FastAPI()
    api = DashboardAPI(db_path)
    set_dashboard_api(api)
    app.include_router(dashboard_router)
    return TestClient(app), api


def test_session_headers_primary_alias_and_blank():
    assert session_fields_from_headers({"X-Otel-Session": " run-1 ", "X-Otel-Session-Step": " plan "}) == ("run-1", "plan")
    assert session_fields_from_headers({"X-Session-ID": "alias-9"}) == ("alias-9", None)
    assert session_fields_from_headers({
        "X-Otel-Session": "canonical",
        "X-Session-ID": "alias",
    }) == ("canonical", None)
    assert session_fields_from_headers({"X-Otel-Session": "   "}) == (None, None)
    assert session_fields_from_headers({}) == (None, None)
    long_id = "s" * 300
    session_id, step = session_fields_from_headers({
        "x-otel-session": long_id,
        "x-otel-session-step": "turn\n1\x00",
    })
    assert session_id == "s" * 256
    assert step == "turn1"


def test_step_flags_mark_failures_and_slow_calls():
    assert step_flags(200, 10) == []
    assert step_flags(500, 10) == ["failed"]
    assert step_flags(404, SLOW_STEP_MS) == ["failed", "slow"]
    assert step_flags(200, SLOW_STEP_MS - 1) == []
    assert step_flags(None, None) == ["failed"]


def test_assemble_session_cumulative_tokens_skip_missing_usage():
    detail = assemble_session("run", [
        {"id": 2, "timestamp": "t1", "method": "POST", "url": "/v1/chat/completions",
         "response_status": 200, "latency_ms": 10, "total_tokens": 10,
         "input_tokens": 8, "output_tokens": 2, "model_name": "openai/gpt-4o",
         "request_body": '{"messages":[{"role":"user","content":"hi"}]}'},
        {"id": 3, "timestamp": "t2", "method": "POST", "url": "/v1/chat/completions",
         "response_status": 500, "latency_ms": 20, "total_tokens": None,
         "input_tokens": None, "output_tokens": None, "model_name": "openai/gpt-4o"},
        {"id": 4, "timestamp": "t3", "method": "POST", "url": "/v1/messages",
         "response_status": 200, "latency_ms": SLOW_STEP_MS, "total_tokens": 5,
         "input_tokens": 1, "output_tokens": 4, "model_name": "openai/gpt-4o"},
    ])
    assert [step["cumulative_total_tokens"] for step in detail["steps"]] == [10, 10, 15]
    assert detail["token_request_count"] == 2
    assert detail["steps"][1]["total_tokens"] is None
    assert detail["steps"][1]["flags"] == ["failed"]
    assert detail["steps"][2]["flags"] == ["slow"]
    assert detail["error_count"] == 1
    assert detail["steps"][0]["request_preview"].startswith('{"messages"')


def test_log_request_without_session_stays_null(tmp_path):
    db = tmp_path / "t.sqlite"
    logger = TelemetryLogger(db)
    _log(logger)
    logger.close()
    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT session_id, session_step FROM requests").fetchone()
    conn.close()
    assert row == (None, None)


def test_legacy_schema_gains_session_columns_and_keeps_old_rows(tmp_path):
    db = tmp_path / "legacy.sqlite"
    _legacy_db(db)
    logger = TelemetryLogger(db)
    logger.close()
    # A second open must be a no-op upgrade.
    logger = TelemetryLogger(db)
    _log(logger, session_id="  run-new  ", session_step="draft", timestamp="2026-04-02T00:00:00+00:00")
    logger.close()

    conn = sqlite3.connect(str(db))
    columns = [row[1] for row in conn.execute("PRAGMA table_info(requests)").fetchall()]
    indexes = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()]
    rows = conn.execute(
        "SELECT session_id, session_step FROM requests ORDER BY id"
    ).fetchall()
    conn.close()
    assert "session_id" in columns
    assert "session_step" in columns
    assert "idx_requests_session_time" in indexes
    assert rows[0] == (None, None)
    assert rows[1] == ("run-new", "draft")


def test_unmigrated_database_lists_no_sessions(tmp_path):
    db = tmp_path / "old.sqlite"
    _legacy_db(db)
    api = DashboardAPI(db)
    assert api.list_sessions()["data"] == []
    assert api.list_sessions()["total"] == 0
    assert api.get_session("anything") is None
    api.close()


def test_list_and_get_session_order_and_rollups(tmp_path):
    db = tmp_path / "t.sqlite"
    logger = TelemetryLogger(db)
    _log(logger, session_id="early", timestamp="2026-04-01T00:00:02+00:00", total_tokens=10, input_tokens=6, output_tokens=4, latency_ms=100)
    _log(
        logger, session_id="early", timestamp="2026-04-01T00:00:01+00:00",
        total_tokens=None, input_tokens=None, output_tokens=None,
        response_status=500, latency_ms=50, url="http://localhost:45638/v1/messages",
    )
    _log(
        logger, session_id="later", timestamp="2026-04-01T01:00:00+00:00",
        total_tokens=7, input_tokens=2, output_tokens=5, latency_ms=SLOW_STEP_MS,
        model_name="openai/gpt-4o-mini", session_step="retry",
        url="http://localhost:45638/v1/responses",
    )
    _log(logger, timestamp="2026-04-01T02:00:00+00:00")
    logger.close()

    api = DashboardAPI(db)
    listed = api.list_sessions(limit=1, offset=0)
    assert listed["total"] == 2
    assert listed["has_more"] is True
    assert listed["data"][0]["session_id"] == "later"
    assert listed["data"][0]["models"] == ["openai/gpt-4o-mini"]
    page2 = api.list_sessions(limit=1, offset=1)
    assert page2["data"][0]["session_id"] == "early"
    assert page2["data"][0]["request_count"] == 2
    assert page2["data"][0]["error_count"] == 1
    assert page2["data"][0]["total_tokens"] == 10
    assert page2["data"][0]["token_request_count"] == 1

    detail = api.get_session("early")
    assert detail is not None
    assert [step["timestamp"] for step in detail["steps"]] == [
        "2026-04-01T00:00:01+00:00",
        "2026-04-01T00:00:02+00:00",
    ]
    assert detail["steps"][0]["flags"] == ["failed"]
    assert detail["steps"][0]["cumulative_total_tokens"] == 0
    assert detail["steps"][1]["cumulative_total_tokens"] == 10
    assert "request_body" not in detail["steps"][1]
    assert detail["steps"][1]["request_preview"]
    slow = api.get_session("later")
    assert slow is not None
    assert slow["steps"][0]["flags"] == ["slow"]
    assert slow["steps"][0]["session_step"] == "retry"
    assert api.get_session("missing") is None
    api.close()


def test_session_routes(tmp_path):
    db = tmp_path / "t.sqlite"
    logger = TelemetryLogger(db)
    _log(logger, session_id="route-1", session_step="plan")
    logger.close()
    client, api = _client(db)
    listing = client.get("/api/sessions")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["data"][0]["session_id"] == "route-1"
    detail = client.get("/api/sessions/route-1")
    assert detail.status_code == 200
    assert detail.json()["steps"][0]["session_step"] == "plan"
    assert detail.json()["steps"][0]["id"]
    missing = client.get("/api/sessions/nope")
    assert missing.status_code == 404
    empty = client.get("/api/sessions/%20")
    assert empty.status_code == 404
    api.close()


def test_dashboard_api_prefers_proxy_and_does_not_read_db(tmp_path):
    db = tmp_path / "t.sqlite"
    logger = TelemetryLogger(db)
    _log(logger, session_id="local-only")
    logger.close()
    api = DashboardAPI(db, proxy_port=9)
    api._http_get = lambda path, params=None: None  # type: ignore[method-assign]
    assert api.list_sessions()["data"] == []
    assert api.get_session("local-only") is None

    payload = {"session_id": "from-proxy", "steps": []}
    api._http_get = lambda path, params=None: (  # type: ignore[method-assign]
        {"data": [payload], "total": 1, "offset": 0, "limit": 50, "has_more": False}
        if path == "/api/sessions"
        else payload
    )
    assert api.list_sessions()["data"][0]["session_id"] == "from-proxy"
    assert api.get_session("from-proxy")["session_id"] == "from-proxy"
    api.close()


def test_log_telemetry_stores_header_and_leaves_missing_null(tmp_path):
    db = tmp_path / "t.sqlite"
    telemetry = TelemetryLogger(db)
    _log_telemetry(
        telemetry, _make_request({"X-Otel-Session": "hdr-1", "X-Otel-Session-Step": "ask"}),
        200, {"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}, "model": "gpt-4"},
        10.0, _make_provider(), request_body='{"model":"gpt-4"}',
    )
    _log_telemetry(
        telemetry, _make_request({"X-Session-ID": "alias-1"}),
        200, {}, 10.0, _make_provider(),
    )
    _log_telemetry(
        telemetry, _make_request(),
        200, {}, 10.0, _make_provider(),
    )
    telemetry.close()
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT session_id, session_step FROM requests ORDER BY id").fetchall()
    conn.close()
    assert rows == [("hdr-1", "ask"), ("alias-1", None), (None, None)]


def _config(tmp_path: Path) -> Config:
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n"
        "  - name: openai\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key: test-key\n"
        "    api_format: openai\n"
    )
    return Config(path)


def _upstream_ok() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {"content-type": "application/json"}
    resp.text = "{}"
    resp.json.return_value = {
        "id": "chatcmpl-1",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "ok"},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        "model": "gpt-4",
    }
    return resp


class _SSE:
    def __init__(self, chunks: list[dict]):
        self.status_code = 200
        self.headers = {"content-type": "text/event-stream"}
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def aiter_lines(self):
        for chunk in self._chunks:
            yield f"data: {json.dumps(chunk)}"
        yield "data: [DONE]"


def test_gateway_paths_share_one_session(tmp_path):
    """Chat, messages, responses, and streaming all persist the same session id."""
    db = tmp_path / "t.sqlite"
    telemetry = TelemetryLogger(db)
    app = create_app(_config(tmp_path), telemetry)
    headers = {"X-Otel-Session": "agent-run"}
    chat = {"model": "openai/gpt-4", "messages": [{"role": "user", "content": "hi"}]}
    with TestClient(app) as client:
        with patch("httpx.AsyncClient.post", return_value=_upstream_ok()):
            assert client.post("/v1/chat/completions", headers={**headers, "X-Otel-Session-Step": "chat"}, json=chat).status_code == 200
            assert client.post(
                "/v1/messages",
                headers={**headers, "X-Otel-Session-Step": "messages"},
                json={"model": "openai/gpt-4", "max_tokens": 16, "messages": [{"role": "user", "content": "hi"}]},
            ).status_code == 200
            assert client.post(
                "/v1/responses",
                headers={**headers, "X-Otel-Session-Step": "responses"},
                json={"model": "openai/gpt-4", "input": "hi"},
            ).status_code == 200
        chunks = [{"choices": [{"delta": {"content": "Hi"}, "index": 0}]}]
        with patch("httpx.AsyncClient.stream", return_value=_SSE(chunks)):
            streamed = client.post(
                "/v1/chat/completions",
                headers={**headers, "X-Otel-Session-Step": "stream"},
                json={**chat, "stream": True},
            )
            assert streamed.status_code == 200
            streamed.read()
    telemetry.close()

    detail = query_session(db, "agent-run")
    assert detail is not None
    assert [step["session_step"] for step in detail["steps"]] == [
        "chat", "messages", "responses", "stream",
    ]
    assert detail["request_count"] == 4
    assert all(step["total_tokens"] is not None or step["session_step"] == "stream" for step in detail["steps"])
    text = format_session_detail(detail)
    assert "agent-run" in text
    assert "cum=" in text
    summary = format_session_summary({
        "session_id": "agent-run",
        "request_count": 4,
        "total_tokens": detail["total_tokens"],
        "error_count": 0,
        "first_timestamp": detail["first_timestamp"],
        "last_timestamp": detail["last_timestamp"],
        "models": detail["models"],
    })
    assert summary.startswith("agent-run")


def test_gateway_omitted_header_logs_null_session(tmp_path):
    db = tmp_path / "t.sqlite"
    telemetry = TelemetryLogger(db)
    app = create_app(_config(tmp_path), telemetry)
    with TestClient(app) as client:
        with patch("httpx.AsyncClient.post", return_value=_upstream_ok()):
            resp = client.post(
                "/v1/chat/completions",
                json={"model": "openai/gpt-4", "messages": [{"role": "user", "content": "hi"}]},
            )
            assert resp.status_code == 200
    telemetry.close()
    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT session_id FROM requests").fetchone()
    conn.close()
    assert row[0] is None

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
    MAX_SESSION_ID_LEN,
    SLOW_STEP_MS,
    assemble_session,
    infer_session_id,
    latest_user_turn_text,
    session_fields_from_headers,
    session_fields_from_request,
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


def test_affinity_headers_rank_below_otel_and_session_id():
    assert session_fields_from_headers({
        "X-Otel-Session": "explicit-1",
        "X-Session-ID": "alias",
        "session_id": "pi",
        "x-session-affinity": "aff",
        "x-client-request-id": "req",
    }) == ("explicit-1", None)
    assert session_fields_from_headers({
        "X-Session-ID": "alias-1",
        "session_id": "pi",
        "x-client-request-id": "req",
    }) == ("alias-1", None)
    assert session_fields_from_headers({"Session_ID": " pi-session "}) == ("pi-session", None)
    assert session_fields_from_headers({"x-session-affinity": "aff"}) == ("aff", None)
    assert session_fields_from_headers({
        "session_id": "   ",
        "x-session-affinity": "",
        "x-client-request-id": "req",
    }) == ("req", None)
    assert session_fields_from_headers({"X-Otel-Session-Step": "plan"}) == (None, "plan")
    assert session_fields_from_headers({
        "X-Otel-Session": "   ",
        "X-Session-ID": "alias-blank-primary",
    }) == ("alias-blank-primary", None)


def _root_chat(extra: list[dict] | None = None) -> dict:
    messages = [
        {"role": "system", "content": "You are a coding agent."},
        {"role": "user", "content": "Rename the helper."},
    ]
    if extra:
        messages.extend(extra)
    return {"model": "openai/gpt-4o", "messages": messages}


def test_header_wins_over_inferred_body():
    body = _root_chat([
        {"role": "assistant", "content": "Done."},
        {"role": "user", "content": "Now add a test."},
    ])
    assert session_fields_from_request({"X-Otel-Session": "explicit-1"}, body) == ("explicit-1", None)
    assert session_fields_from_request(
        {"X-Session-ID": "alias-1", "session_id": "pi"},
        json.dumps(body),
    )[0] == "alias-1"
    assert session_fields_from_request({"x-session-affinity": "aff"}, body)[0] == "aff"
    inferred, step = session_fields_from_request(
        {"X-Otel-Session": "  ", "X-Session-ID": "", "X-Otel-Session-Step": "plan"},
        body,
    )
    assert inferred == infer_session_id(body)
    assert inferred is not None and inferred.startswith("inferred-")
    assert step == "plan"


def test_growing_history_keeps_the_same_inferred_id():
    first = _root_chat()
    grown = _root_chat([
        {"role": "assistant", "content": "Done.", "tool_calls": [{"id": "c1", "function": {"name": "read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "file contents"},
        {"role": "user", "content": "Now add a test."},
    ])
    image_shifted = {
        "messages": [
            {"role": "developer", "content": " You are a coding agent. "},
            {"role": "user", "content": [
                {"type": "text", "text": "Rename the helper."},
                {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
            ]},
            {"role": "assistant", "content": "Done."},
            {"role": "user", "content": [
                {"type": "text", "text": "Rename the helper."},
                {"type": "image_url", "image_url": {"url": "https://example.test/b.png"}},
            ]},
        ],
    }
    assert infer_session_id(first) == infer_session_id(grown) == infer_session_id(image_shifted)
    assert infer_session_id(first) != infer_session_id(
        {"messages": [{"role": "system", "content": "You are a coding agent."}, {"role": "user", "content": "Different task."}]}
    )
    assert infer_session_id(first) != infer_session_id(
        {"messages": [{"role": "system", "content": "Different instructions."}, {"role": "user", "content": "Rename the helper."}]}
    )


def test_inferred_id_is_a_stable_pure_function():
    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert infer_session_id(body) == "inferred-dfb4eb0c36a42d62"
    assert infer_session_id(json.dumps(body)) == "inferred-dfb4eb0c36a42d62"
    assert infer_session_id(json.dumps(body).encode()) == "inferred-dfb4eb0c36a42d62"
    assert infer_session_id({"messages": [{"role": "user", "content": " hi "}]}) == "inferred-dfb4eb0c36a42d62"
    assert len("inferred-dfb4eb0c36a42d62") <= MAX_SESSION_ID_LEN
    # Unrelated chats that share this first user text share the id.
    assert infer_session_id({"messages": [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "a different reply"},
    ]}) == "inferred-dfb4eb0c36a42d62"


def test_empty_or_non_conversation_body_stays_null():
    assert infer_session_id(None) is None
    assert infer_session_id("") is None
    assert infer_session_id(b"\xff") is None
    assert infer_session_id("not json") is None
    assert infer_session_id("[]") is None
    assert infer_session_id({}) is None
    assert infer_session_id({"messages": []}) is None
    assert infer_session_id({"messages": [{"role": "system", "content": "only a prompt"}]}) is None
    assert infer_session_id({"messages": [{"role": "user", "content": "   "}]}) is None
    assert infer_session_id({"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.test/a.png"}}]}]}) is None
    assert infer_session_id({"model": "openai/dall-e-3", "prompt": "a cat", "n": 1}) is None
    assert infer_session_id("multipart form: ['image', 'prompt']") is None
    assert session_fields_from_request({}, None) == (None, None)
    assert session_fields_from_request({}, {"prompt": "a cat"})[1] is None


def test_anthropic_and_responses_roots_match_chat():
    chat = _root_chat()
    expected = infer_session_id(chat)
    anthropic_turn1 = {
        "system": [{"type": "text", "text": "You are a coding agent.", "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": "Rename the helper."}],
    }
    anthropic_turn2 = {
        "system": "You are a coding agent.",
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "Rename the helper."}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Done."}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}, {"type": "text", "text": "Now add a test."}]},
        ],
    }
    responses_string = {"instructions": "You are a coding agent.", "input": "Rename the helper."}
    responses_grown = {
        "instructions": "You are a coding agent.",
        "input": [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Rename the helper."}]},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Done."}]},
            {"type": "function_call", "name": "read", "arguments": "{}"},
            {"role": "user", "content": "Now add a test."},
        ],
    }
    assert infer_session_id(anthropic_turn1) == expected
    assert infer_session_id(anthropic_turn2) == expected
    assert infer_session_id(responses_string) == expected
    assert infer_session_id(responses_grown) == expected
    assert infer_session_id({"input": ["Rename the helper."]}) == infer_session_id(
        {"messages": [{"role": "user", "content": "Rename the helper."}]}
    )
    # Latest-turn-only input has no shared root with the original conversation.
    assert infer_session_id({"instructions": "You are a coding agent.", "input": "Now add a test."}) != expected


def test_step_flags_mark_failures_and_slow_calls():
    assert step_flags(200, 10) == []
    assert step_flags(500, 10) == ["failed"]
    assert step_flags(404, SLOW_STEP_MS) == ["failed", "slow"]
    assert step_flags(200, SLOW_STEP_MS - 1) == []
    assert step_flags(None, None) == ["failed"]


def test_latest_user_turn_text_ignores_tool_results():
    assert latest_user_turn_text({"messages": [
        {"role": "user", "content": "Rename the helper."},
        {"role": "assistant", "content": "ok"},
        {"role": "tool", "content": "file"},
    ]}) == "Rename the helper."
    assert latest_user_turn_text({
        "messages": [
            {"role": "user", "content": "Rename the helper."},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]},
        ]
    }) == "Rename the helper."
    assert latest_user_turn_text({
        "messages": [
            {"role": "user", "content": "Rename the helper."},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t", "content": "ok"},
                {"type": "text", "text": "Now add a test."},
            ]},
        ]
    }) == "Now add a test."
    assert latest_user_turn_text({"instructions": "sys", "input": [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Rename the helper."}]},
        {"type": "function_call_output", "call_id": "c", "output": "ok"},
    ]}) == "Rename the helper."
    assert latest_user_turn_text({"model": "dall-e-3", "prompt": "a cat"}) is None
    assert latest_user_turn_text(None) is None
    assert latest_user_turn_text("not json") is None


def test_assemble_session_groups_a_tool_loop_and_splits_on_a_new_user_message():
    detail = assemble_session("run", [
        {"id": 1, "timestamp": "t1", "method": "POST", "url": "/v1/chat/completions",
         "response_status": 200, "latency_ms": 10, "total_tokens": 10,
         "input_tokens": 8, "output_tokens": 2, "session_step": "plan",
         "request_body": '{"messages":[{"role":"user","content":"Rename the helper."}]}'},
        {"id": 2, "timestamp": "t2", "method": "POST", "url": "/v1/chat/completions",
         "response_status": 200, "latency_ms": 12, "total_tokens": 4,
         "input_tokens": 3, "output_tokens": 1, "session_step": "tool",
         "request_body": json.dumps({"messages": [
             {"role": "user", "content": "Rename the helper."},
             {"role": "assistant", "content": "Reading."},
             {"role": "tool", "content": "old name"},
         ]})},
        {"id": 3, "timestamp": "t3", "method": "POST", "url": "/v1/chat/completions",
         "response_status": 200, "latency_ms": 8, "total_tokens": 6,
         "input_tokens": 4, "output_tokens": 2, "session_step": "edit",
         "request_body": json.dumps({"messages": [
             {"role": "user", "content": "Rename the helper."},
             {"role": "assistant", "content": "Done."},
             {"role": "user", "content": "Now add a test."},
         ]})},
        {"id": 4, "timestamp": "t4", "method": "POST", "url": "/v1/images/generations",
         "response_status": 200, "latency_ms": 5, "total_tokens": None,
         "request_body": '{"model":"dall-e-3","prompt":"a cat"}'},
    ])
    assert [step["turn_index"] for step in detail["steps"]] == [1, 1, 2, 3]
    assert detail["steps"][0]["turn_label"] == "Rename the helper."
    assert detail["steps"][1]["turn_label"] == "Rename the helper."
    assert detail["steps"][1]["session_step"] == "tool"
    assert detail["steps"][2]["turn_label"] == "Now add a test."
    assert detail["steps"][3]["turn_label"] is None
    assert "request_body" not in detail["steps"][0]
    text = format_session_detail(detail)
    assert "turn 1  Rename the helper." in text
    assert "turn 2  Now add a test." in text


def test_session_route_exposes_turn_indexes(tmp_path):
    db = tmp_path / "t.sqlite"
    logger = TelemetryLogger(db)
    _log(
        logger, session_id="run", session_step="plan",
        timestamp="2026-04-01T00:00:01+00:00",
        request_body='{"messages":[{"role":"user","content":"Rename the helper."}]}',
    )
    _log(
        logger, session_id="run", session_step="tool",
        timestamp="2026-04-01T00:00:02+00:00",
        request_body=json.dumps({"messages": [
            {"role": "user", "content": "Rename the helper."},
            {"role": "tool", "content": "old name"},
        ]}),
    )
    _log(
        logger, session_id="other",
        timestamp="2026-04-01T00:00:03+00:00",
        request_body='{"messages":[{"role":"user","content":"Rename the helper."}]}',
    )
    logger.close()
    client, api = _client(db)
    detail = client.get("/api/sessions/run").json()
    assert [step["turn_index"] for step in detail["steps"]] == [1, 1]
    assert detail["request_count"] == 2
    assert "request_body" not in detail["steps"][0]
    other = client.get("/api/sessions/other").json()
    assert [step["id"] for step in other["steps"]] != [step["id"] for step in detail["steps"]]
    assert other["steps"][0]["turn_index"] == 1
    api.close()


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
    assert "idx_requests_session_summary" in indexes
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


def _select_plans(storage, fn) -> tuple[object, list[str]]:
    """Run ``fn`` and return its result plus EXPLAIN plans for its SELECTs."""
    conn = storage._get_conn()
    statements: list[str] = []

    def trace(sql: str) -> None:
        if sql.lstrip().upper().startswith("SELECT"):
            statements.append(sql)

    conn.set_trace_callback(trace)
    try:
        result = fn()
    finally:
        conn.set_trace_callback(None)
    plans = []
    for sql in statements:
        rows = conn.execute("EXPLAIN QUERY PLAN " + sql).fetchall()
        plans.append(" | ".join(str(row[-1]) for row in rows))
    return result, plans


def test_list_sessions_reads_covering_index_not_bodies(tmp_path):
    """Session rollups stay correct and come from idx_requests_session_summary.

    ``idx_requests_session_time`` groups by session id, then looks up each
    row. Token and status columns sit after the body columns, so that
    lookup reads request and response overflow pages for every tagged row.
    """
    logger = TelemetryLogger(tmp_path / "covering.sqlite")
    body = "y" * 2048
    conn = logger.storage._get_conn()
    rows = []
    for i in range(30):
        later = i >= 10
        sid = "later" if later else "early"
        minute = i - 10 if later else i
        hour = 1 if later else 0
        status = 500 if i == 3 else 200
        reported = i != 3
        model = "openai/gpt-4o-mini" if later and i % 2 == 0 else "openai/gpt-4o"
        upstream = "https://b.example" if later else "https://a.example"
        # Early rows are real chats so the detail page still groups turns.
        # The first five share a user text; the next five start the next turn.
        if later:
            request_body = body
        else:
            user = "alpha question" if i < 5 else "beta question"
            request_body = json.dumps({"messages": [{"role": "user", "content": user}]})
        rows.append((
            f"2026-04-01T{hour:02d}:{minute:02d}:00+00:00",
            "POST", "https://example.test/v1/chat/completions", upstream, "{}",
            request_body, status, "{}", body, 25.0 if later else 10.0, model,
            8 if reported else None, 2 if reported else None, 10 if reported else None,
            None, None, "openai", sid, None,
        ))
    rows.append((
        "2026-04-01T03:00:00+00:00", "POST", "https://example.test/v1", "https://a.example", "{}",
        body, 200, "{}", body, 5.0, "openai/gpt-4o",
        1, 1, 2, None, None, "openai", None, None,
    ))
    rows.append((
        "2026-04-01T03:01:00+00:00", "POST", "https://example.test/v1", "https://a.example", "{}",
        body, 200, "{}", body, 5.0, "openai/gpt-4o",
        1, 1, 2, None, None, "openai", "", None,
    ))
    conn.executemany(
        """INSERT INTO requests
           (timestamp, method, url, upstream, request_headers, request_body,
            response_status, response_headers, response_body, latency_ms, model_name,
            input_tokens, output_tokens, total_tokens, cache_read_tokens,
            cache_creation_tokens, format, session_id, session_step)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()

    listed, plans = _select_plans(
        logger.storage, lambda: logger.storage.list_sessions(limit=1, offset=0),
    )
    early = logger.storage.list_sessions(limit=1, offset=1)["data"][0]
    detail = logger.storage.get_session("early")
    logger.close()

    assert listed["total"] == 2
    assert listed["has_more"] is True
    assert listed["data"][0]["session_id"] == "later"
    assert listed["data"][0]["request_count"] == 20
    assert listed["data"][0]["total_tokens"] == 200
    assert listed["data"][0]["input_tokens"] == 160
    assert listed["data"][0]["output_tokens"] == 40
    assert listed["data"][0]["token_request_count"] == 20
    assert listed["data"][0]["error_count"] == 0
    assert listed["data"][0]["total_latency_ms"] == 500
    assert set(listed["data"][0]["models"]) == {"openai/gpt-4o", "openai/gpt-4o-mini"}
    assert listed["data"][0]["upstreams"] == ["https://b.example"]
    assert early["session_id"] == "early"
    assert early["request_count"] == 10
    assert early["error_count"] == 1
    assert early["total_tokens"] == 90
    assert early["token_request_count"] == 9
    assert early["total_latency_ms"] == 100

    summary_plans = [plan for plan in plans if "group_concat" in plan or "idx_requests_session_summary" in plan]
    count_plans = [plan for plan in plans if "subquery" in plan]
    assert summary_plans, plans
    assert count_plans, plans
    for plan in summary_plans:
        assert "COVERING INDEX idx_requests_session_summary" in plan, plan
        assert "idx_requests_session_time" not in plan, plan
    for plan in count_plans:
        assert "COVERING INDEX idx_requests_session_time" in plan, plan

    assert detail is not None
    assert detail["request_count"] == 10
    assert [step["turn_index"] for step in detail["steps"]] == [1, 1, 1, 1, 1, 2, 2, 2, 2, 2]
    assert detail["steps"][0]["turn_label"] == "alpha question"
    assert detail["steps"][5]["turn_label"] == "beta question"
    assert detail["steps"][3]["flags"] == ["failed"]
    assert "request_body" not in detail["steps"][0]


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


def test_request_detail_includes_session_fields(tmp_path):
    """Detail keeps the stored session id so the page can link to that trajectory."""
    db = tmp_path / "t.sqlite"
    logger = TelemetryLogger(db)
    inferred = infer_session_id({"messages": [{"role": "user", "content": "hello"}]})
    assert inferred is not None and inferred.startswith("inferred-")
    _log(logger, session_id="  agent-run  ", session_step=" plan ")
    _log(logger, session_id=inferred, timestamp="2026-04-01T00:00:01+00:00")
    _log(logger, timestamp="2026-04-01T00:00:02+00:00")
    logger.close()
    client, api = _client(db)

    tagged = client.get("/api/requests/1")
    assert tagged.status_code == 200
    body = tagged.json()
    assert body["session_id"] == "agent-run"
    assert body["session_step"] == "plan"
    assert "messages" in body

    grouped = client.get("/api/requests/2").json()
    assert grouped["session_id"] == inferred
    assert grouped["session_step"] is None

    bare = client.get("/api/requests/3").json()
    assert bare["session_id"] is None
    assert bare["session_step"] is None

    downloaded = client.get("/api/requests/1/download")
    assert downloaded.status_code == 200
    assert downloaded.json()["session_id"] == "agent-run"
    assert downloaded.json()["session_step"] == "plan"

    listed = client.get("/api/sessions").json()
    assert {row["session_id"] for row in listed["data"]} == {"agent-run", inferred}
    trajectory = client.get(f"/api/sessions/{inferred}").json()
    assert trajectory["request_count"] == 1
    assert [step["id"] for step in trajectory["steps"]] == [2]
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


def test_log_telemetry_infers_session_and_keeps_explicit_header(tmp_path):
    db = tmp_path / "t.sqlite"
    telemetry = TelemetryLogger(db)
    first = json.dumps(_root_chat())
    grown = json.dumps(_root_chat([
        {"role": "assistant", "content": "Done."},
        {"role": "user", "content": "Now add a test."},
    ]))
    anthropic = json.dumps({
        "system": "You are a coding agent.",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "Rename the helper."}]}],
    })
    responses = json.dumps({"instructions": "You are a coding agent.", "input": "Rename the helper."})
    expected = infer_session_id(first)
    _log_telemetry(telemetry, _make_request(), 200, {}, 10.0, _make_provider(), request_body=first)
    _log_telemetry(telemetry, _make_request(), 200, {}, 11.0, _make_provider(), request_body=grown)
    _log_telemetry(telemetry, _make_request(), 200, {}, 12.0, _make_provider(), request_body=anthropic)
    _log_telemetry(telemetry, _make_request(), 200, {}, 13.0, _make_provider(), request_body=responses)
    _log_telemetry(
        telemetry, _make_request({"X-Otel-Session": "explicit-1"}),
        200, {}, 14.0, _make_provider(), request_body=grown,
    )
    _log_telemetry(
        telemetry, _make_request({"X-Otel-Session-Step": "plan"}),
        200, {}, 15.0, _make_provider(), request_body=first,
    )
    _log_telemetry(
        telemetry, _make_request(), 200, {}, 16.0, _make_provider(),
        request_body=first, log_body=False,
    )
    _log_telemetry(
        telemetry, _make_request(), 200, {}, 17.0, _make_provider(),
        request_body='{"model":"openai/dall-e-3","prompt":"a cat"}',
    )
    _log_telemetry(telemetry, _make_request(), 200, {}, 18.0, _make_provider(), request_body="{}")
    telemetry.close()

    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT session_id, session_step, request_body FROM requests ORDER BY id"
    ).fetchall()
    conn.close()
    assert rows[0][0] == rows[1][0] == rows[2][0] == rows[3][0] == expected
    assert rows[0][1] is None
    assert rows[4] == ("explicit-1", None, grown)
    assert rows[5][0] == expected and rows[5][1] == "plan"
    assert rows[6][0] == expected and rows[6][2] == ""
    assert rows[7][0] is None
    assert rows[8][0] is None


def test_gateway_infers_one_trajectory_from_growing_history(tmp_path):
    """No session header, same first user turn, longer history → one session."""
    db = tmp_path / "t.sqlite"
    telemetry = TelemetryLogger(db)
    app = create_app(_config(tmp_path), telemetry)
    turn1 = {
        "model": "openai/gpt-4",
        "messages": [
            {"role": "system", "content": "You are a coding agent."},
            {"role": "user", "content": "Rename the helper."},
        ],
    }
    turn2 = {
        "model": "openai/gpt-4",
        "messages": [
            *turn1["messages"],
            {"role": "assistant", "content": "Done."},
            {"role": "user", "content": "Now add a test."},
        ],
    }
    turn3 = {
        "model": "openai/gpt-4",
        "stream": True,
        "messages": [
            *turn2["messages"],
            {"role": "assistant", "content": "Added."},
            {"role": "user", "content": "Ship it."},
        ],
    }
    anthropic = {
        "model": "openai/gpt-4",
        "max_tokens": 16,
        "system": "You are a coding agent.",
        "messages": [
            {"role": "user", "content": "Rename the helper."},
            {"role": "assistant", "content": "Done."},
            {"role": "user", "content": "Now add a test."},
        ],
    }
    responses = {
        "model": "openai/gpt-4",
        "instructions": "You are a coding agent.",
        "input": [
            {"role": "user", "content": "Rename the helper."},
            {"role": "assistant", "content": "Done."},
            {"role": "user", "content": "Now add a test."},
        ],
    }
    with TestClient(app) as client:
        with patch("httpx.AsyncClient.post", return_value=_upstream_ok()):
            assert client.post("/v1/chat/completions", json=turn1).status_code == 200
            assert client.post("/v1/chat/completions", json=turn2).status_code == 200
            assert client.post(
                "/v1/chat/completions",
                headers={"X-Otel-Session": "explicit-1"},
                json=turn2,
            ).status_code == 200
            assert client.post(
                "/v1/messages",
                json=anthropic,
            ).status_code == 200
            assert client.post("/v1/responses", json=responses).status_code == 200
            assert client.post(
                "/v1/chat/completions",
                json={"model": "openai/gpt-4"},
            ).status_code == 200
        chunks = [{"choices": [{"delta": {"content": "Hi"}, "index": 0}]}]
        with patch("httpx.AsyncClient.stream", return_value=_SSE(chunks)):
            streamed = client.post("/v1/chat/completions", json=turn3)
            assert streamed.status_code == 200
            streamed.read()
        listing = client.get("/api/sessions")
        assert listing.status_code == 200
        listed = listing.json()
    telemetry.close()

    inferred = infer_session_id(turn1)
    assert inferred == infer_session_id(turn2) == infer_session_id(anthropic) == infer_session_id(responses)
    assert {row["session_id"] for row in listed["data"]} == {inferred, "explicit-1"}
    assert listed["total"] == 2

    detail = query_session(db, inferred)
    assert detail is not None
    assert detail["request_count"] == 5
    assert all(step["session_step"] is None for step in detail["steps"])
    text = format_session_detail(detail)
    assert inferred in text
    explicit = query_session(db, "explicit-1")
    assert explicit is not None
    assert explicit["request_count"] == 1

    conn = sqlite3.connect(str(db))
    nulls = conn.execute("SELECT COUNT(*) FROM requests WHERE session_id IS NULL").fetchone()[0]
    conn.close()
    assert nulls == 1

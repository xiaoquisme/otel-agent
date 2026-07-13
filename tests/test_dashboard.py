"""Tests for dashboard API and FastAPI routes."""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
from fastapi import FastAPI
from fastapi.testclient import TestClient
from otel_agent.dashboard.api import DashboardAPI, CountCache
from otel_agent.dashboard.routes import router as dashboard_router, set_api as set_dashboard_api

# ------------------------------------------------------------------
# Reusable fixture helpers (T001)
# ------------------------------------------------------------------

def _current_day_utc_range() -> tuple[str, str]:
    """Return (start, end) UTC ISO-8601 strings for the current calendar day."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = (now.replace(hour=0, minute=0, second=0, microsecond=0)
           + timedelta(days=1)).isoformat()
    return start, end


def _day_ago_utc_range() -> tuple[str, str]:
    """Return (start, end) for yesterday — should match nothing for current-day tests."""
    now = datetime.now(timezone.utc)
    start = (now.replace(hour=0, minute=0, second=0, microsecond=0)
             - timedelta(days=1)).isoformat()
    end = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    return start, end

def _seed_usage_record(
    db_path: Path,
    *,
    timestamp: str | None = None,
    model_name: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    response_status: int = 200,
) -> None:
    """Insert one request record with analytics fields into an existing DuckDB."""
    conn = duckdb.connect(str(db_path))
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO requests
           (timestamp, method, url, upstream, request_headers, request_body,
            response_status, response_headers, response_body, latency_ms,
            model_name, input_tokens, output_tokens, total_tokens)
           VALUES (?, 'POST', '/test', '', '{}', '{}', ?, '{}', '{}', 1.0,
                   ?, ?, ?, ?)""",
        (timestamp, response_status, model_name, input_tokens, output_tokens, total_tokens),
    )
    conn.commit()
    conn.close()

def _create_usage_db(db_path: Path, records: list[dict]) -> None:
    """Create a DuckDB with the standard schema and seed multiple usage records."""
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
            latency_ms DOUBLE,
            model_name TEXT,
            input_tokens BIGINT,
            output_tokens BIGINT,
            total_tokens BIGINT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp)")
    for r in records:
        conn.execute(
            """INSERT INTO requests
               (timestamp, method, url, upstream, request_headers, request_body,
                response_status, response_headers, response_body, latency_ms,
                model_name, input_tokens, output_tokens, total_tokens)
               VALUES (?, ?, ?, '', '{}', '{}', ?, '{}', '{}', 1.0,
                       ?, ?, ?, ?)""",
            (
                r.get("timestamp", datetime.now(timezone.utc).isoformat()),
                r.get("method", "POST"),
                r.get("url", "/test"),
                r.get("response_status", 200),
                r.get("model_name"),
                r.get("input_tokens"),
                r.get("output_tokens"),
                r.get("total_tokens"),
            ),
        )
    conn.commit()
    conn.close()


def _create_test_db(db_path: Path, n: int = 5) -> None:
    """Create a test database with n requests."""
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
            latency_ms DOUBLE,
            model_name TEXT,
            input_tokens BIGINT,
            output_tokens BIGINT,
            total_tokens BIGINT
        )
    """)
    for i in range(1, n + 1):
        conn.execute(
            "INSERT INTO requests (timestamp, method, url, upstream, request_headers, "
            "request_body, response_status, response_headers, response_body, latency_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"2026-06-26T10:00:{i:02d}Z",
                "POST" if i % 2 else "GET",
                f"/openai/v1/chat/completions/{i}",
                f"https://api.openai.com/v1/chat/completions/{i}",
                '{"Authorization": "Bearer sk-test"}',
                '{"model":"gpt-4"}',
                200 if i < 4 else 500,
                '{"content-type": "application/json"}',
                '{"choices":[]}',
                100.0 * i,
            ),
        )
    conn.close()


# ------------------------------------------------------------------
# DashboardAPI unit tests (direct storage path)
# ------------------------------------------------------------------

def test_get_requests_empty(tmp_path):
    db = tmp_path / "test.duckdb"
    api = DashboardAPI(db)
    result = api.get_requests()
    assert result == {"data": [], "total": 0, "cursor": 0, "next_cursor": 0, "has_more": False}
    api.close()


def test_get_requests_with_data(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    result = api.get_requests()
    assert result["total"] == 5
    assert len(result["data"]) == 5
    assert result["cursor"] == 0
    assert result["has_more"] is False
    api.close()


def test_get_requests_cursor_pagination(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 10)
    api = DashboardAPI(db)
    result = api.get_requests(limit=3)
    assert result["total"] == 10
    assert len(result["data"]) == 3
    assert result["has_more"] is True
    next_cursor = result["next_cursor"]

    result2 = api.get_requests(cursor=next_cursor, limit=3)
    assert len(result2["data"]) == 3
    assert result["data"][0]["id"] != result2["data"][0]["id"]
    api.close()


def test_get_requests_search(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    result = api.get_requests(search="completions/3")
    assert result["total"] == 1
    assert result["data"][0]["url"] == "/openai/v1/chat/completions/3"
    api.close()


def test_get_requests_filter_method(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    result = api.get_requests(method="POST")
    assert result["total"] == 3
    for r in result["data"]:
        assert r["method"] == "POST"
    api.close()


def test_get_requests_filter_status(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    result = api.get_requests(status=500)
    assert result["total"] == 2
    for r in result["data"]:
        assert r["response_status"] == 500
    api.close()


def test_get_request_detail(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    api = DashboardAPI(db)
    result = api.get_request(2)
    assert result is not None
    assert result["id"] == 2
    assert result["method"] == "GET"
    assert isinstance(result["request_headers"], dict)
    api.close()


def test_get_request_not_found(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    api = DashboardAPI(db)
    assert api.get_request(999) is None
    api.close()


def test_get_all_filtered(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    result = api.get_all_filtered(method="POST")
    assert len(result) == 3
    assert all(r["method"] == "POST" for r in result)
    api.close()


def test_count_cache():
    cache = CountCache(ttl=5.0)
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE t (id INTEGER)")
    for i in range(10):
        conn.execute("INSERT INTO t VALUES (?)", (i,))

    # First call queries DB
    result1 = cache.get("test", conn, "SELECT COUNT(*) FROM t", [])
    assert result1 == 10

    # Second call returns cached
    conn.execute("INSERT INTO t VALUES (99)")
    result2 = cache.get("test", conn, "SELECT COUNT(*) FROM t", [])
    assert result2 == 10  # Still cached

    # After clear, gets fresh value
    cache.clear()
    result3 = cache.get("test", conn, "SELECT COUNT(*) FROM t", [])
    assert result3 == 11
    conn.close()


def test_persistent_connection(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    api = DashboardAPI(db)
    r1 = api.get_requests()
    r2 = api.get_requests()
    r3 = api.get_request(1)
    assert r1["total"] == 3
    assert r2["total"] == 3
    assert r3["id"] == 1
    api.close()


def test_historical_requests_visible(tmp_path):
    """All requests in DB are returned on first call, not just new ones."""
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 10)
    api = DashboardAPI(db)
    result = api.get_requests(limit=50)
    assert result["total"] == 10
    assert len(result["data"]) == 10
    api.close()


def test_historical_requests_after_new_data(tmp_path):
    """Historical + new requests are all visible."""
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    r1 = api.get_requests(limit=50)
    assert r1["total"] == 5
    api.close()

    # Add more requests directly to DB
    conn = duckdb.connect(str(db))
    for i in range(6, 9):
        conn.execute(
            "INSERT INTO requests (timestamp, method, url, upstream, request_headers, "
            "request_body, response_status, response_headers, response_body, latency_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"2026-06-27T10:00:{i:02d}Z", "GET", f"/test/{i}", f"https://test.com/{i}",
             "{}", "{}", 200, "{}", "{}", 50.0),
        )
    conn.close()

    api.clear_cache()
    r2 = api.get_requests(limit=50)
    assert r2["total"] == 8
    assert len(r2["data"]) == 8
    api.close()


def test_empty_database_no_crash(tmp_path):
    """Non-existent database returns empty result without error."""
    db = tmp_path / "nonexistent" / "test.duckdb"
    api = DashboardAPI(db)
    result = api.get_requests()
    assert result == {"data": [], "total": 0, "cursor": 0, "next_cursor": 0, "has_more": False}
    assert api.get_request(1) is None
    assert api.get_all_filtered() == []
    api.close()


# ------------------------------------------------------------------
# FastAPI route tests (TestClient)
# ------------------------------------------------------------------

def _make_client(db_path: Path) -> TestClient:
    """Create a FastAPI TestClient wired to a DashboardAPI for the given db_path."""
    app = FastAPI()
    api = DashboardAPI(db_path)
    set_dashboard_api(api)
    app.include_router(dashboard_router)
    return TestClient(app), api


def test_route_events_removed(tmp_path):
    """GET /api/events returns 404 after SSE removal."""
    db = tmp_path / "test.duckdb"
    client, api = _make_client(db)
    resp = client.get("/api/events")
    assert resp.status_code == 404
    api.close()


def test_route_requests_empty(tmp_path):
    db = tmp_path / "test.duckdb"
    client, api = _make_client(db)
    resp = client.get("/api/requests")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["data"] == []
    api.close()


def test_route_requests_with_data(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    client, api = _make_client(db)
    resp = client.get("/api/requests")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["data"]) == 5
    api.close()


def test_route_requests_pagination(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 10)
    client, api = _make_client(db)
    resp = client.get("/api/requests?limit=3")
    body = resp.json()
    assert body["total"] == 10
    assert len(body["data"]) == 3
    assert body["has_more"] is True
    # Fetch next page
    resp2 = client.get(f"/api/requests?limit=3&cursor={body['next_cursor']}")
    body2 = resp2.json()
    assert len(body2["data"]) == 3
    assert body["data"][0]["id"] != body2["data"][0]["id"]
    api.close()


def test_route_requests_search(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    client, api = _make_client(db)
    resp = client.get("/api/requests?search=completions/3")
    body = resp.json()
    assert body["total"] == 1
    assert body["data"][0]["url"] == "/openai/v1/chat/completions/3"
    api.close()


def test_route_requests_filter_method(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    client, api = _make_client(db)
    resp = client.get("/api/requests?method=POST")
    body = resp.json()
    assert body["total"] == 3
    for r in body["data"]:
        assert r["method"] == "POST"
    api.close()


def test_route_requests_filter_status(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    client, api = _make_client(db)
    resp = client.get("/api/requests?status=500")
    body = resp.json()
    assert body["total"] == 2
    for r in body["data"]:
        assert r["response_status"] == 500
    api.close()


def test_route_request_detail(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    client, api = _make_client(db)
    resp = client.get("/api/requests/2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 2
    assert body["method"] == "GET"
    api.close()


def test_route_request_not_found(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    client, api = _make_client(db)
    resp = client.get("/api/requests/999")
    assert resp.status_code == 404
    api.close()


def test_route_request_invalid_id(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    client, api = _make_client(db)
    resp = client.get("/api/requests/abc")
    assert resp.status_code == 422  # FastAPI validation error
    api.close()


def test_route_export_csv(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    client, api = _make_client(db)
    resp = client.get("/api/export?format=csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    assert "attachment" in resp.headers.get("content-disposition", "")
    api.close()


def test_route_export_json(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    client, api = _make_client(db)
    resp = client.get("/api/export?format=json")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    body = resp.json()
    assert len(body) == 5
    api.close()


def test_route_cache_clear(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    client, api = _make_client(db)
    resp = client.get("/api/cache/clear")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    api.close()


def test_route_usage_missing_params(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    client, api = _make_client(db)
    resp = client.get("/api/usage")
    assert resp.status_code == 422  # Missing required query params
    api.close()


def test_route_usage_invalid_format(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    client, api = _make_client(db)
    resp = client.get("/api/usage?start=not-a-date&end=also-not")
    assert resp.status_code == 400
    assert "Invalid datetime" in resp.json()["error"]
    api.close()


def test_route_usage_end_before_start(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    client, api = _make_client(db)
    # Use Z suffix to avoid URL encoding issues with +00:00
    start, end = _current_day_utc_range()
    start_z = start.replace("+00:00", "Z")
    end_z = end.replace("+00:00", "Z")
    resp = client.get(f"/api/usage?start={end_z}&end={start_z}")
    assert resp.status_code == 400
    assert "end must be after start" in resp.json()["error"]
    api.close()


def test_route_usage_range_too_long(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    client, api = _make_client(db)
    start = "2026-01-01T00:00:00Z"
    end = "2026-01-04T00:00:00Z"  # 3 days > 48h
    resp = client.get(f"/api/usage?start={start}&end={end}")
    assert resp.status_code == 400
    assert "48 hours" in resp.json()["error"]
    api.close()


def test_route_usage_valid_range(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    client, api = _make_client(db)
    start, end = _current_day_utc_range()
    start_z = start.replace("+00:00", "Z")
    end_z = end.replace("+00:00", "Z")
    resp = client.get(f"/api/usage?start={start_z}&end={end_z}")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_tokens" in body
    assert "models" in body
    api.close()


def test_route_usage_yesterday_empty(tmp_path):
    """Yesterday's range should return zero usage for today-only data."""
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 3)
    client, api = _make_client(db)
    start, end = _day_ago_utc_range()
    start_z = start.replace("+00:00", "Z")
    end_z = end.replace("+00:00", "Z")
    resp = client.get(f"/api/usage?start={start_z}&end={end_z}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_tokens"] == 0
    api.close()

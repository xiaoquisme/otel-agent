"""Tests for dashboard API with DuckDB backend."""

import json
import tempfile
from pathlib import Path

import duckdb

from otel_agent.dashboard.api import DashboardAPI, CountCache


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
            latency_ms DOUBLE
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


def test_get_requests_since(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    result = api.get_requests_since(3)
    assert len(result) == 2
    assert all(r["id"] > 3 for r in result)
    api.close()


def test_get_max_id(tmp_path):
    db = tmp_path / "test.duckdb"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    assert api.get_max_id() == 5
    api.close()


def test_get_max_id_empty(tmp_path):
    db = tmp_path / "test.duckdb"
    api = DashboardAPI(db)
    assert api.get_max_id() == 0
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
    assert api.get_requests_since(0) == []
    assert api.get_max_id() == 0
    assert api.get_all_filtered() == []
    api.close()


# ------------------------------------------------------------------
# BUG-002: Proxy URL caching — health check timeout scenario
# ------------------------------------------------------------------

def test_proxy_url_caching_prevents_fallback(tmp_path):
    """When proxy was reachable then goes down, DashboardAPI keeps using cached URL.

    BUG-002: A slow health check should NOT cause fallback to direct DuckDB.
    The cached proxy URL should be reused for up to 60s after the proxy
    becomes unreachable.
    """
    import time as _time
    from unittest.mock import patch, MagicMock

    db_path = tmp_path / "test.duckdb"
    _create_test_db(db_path, n=3)

    api = DashboardAPI(db_path, proxy_port=19999)

    # Simulate: proxy was reachable, cache is warm
    api._proxy_url_cache = "http://127.0.0.1:19999"
    api._proxy_url_cache_time = _time.monotonic()
    api._proxy_last_fail_time = 0.0

    # Now simulate health check failure (proxy busy)
    with patch("otel_agent.dashboard.api.urllib.request.urlopen", side_effect=TimeoutError("busy")):
        # Should still return cached URL (within 60s window)
        result = api._proxy_url()
        assert result == "http://127.0.0.1:19999", "Should return cached URL even when health check fails"

    api.close()


def test_proxy_url_cache_expires_after_60s(tmp_path):
    """After 60s of proxy being unreachable, fall back to direct DuckDB.

    BUG-002: If the proxy has been unreachable for > 60s, the cache should
    expire and allow fallback to direct DuckDB connection.
    """
    import time as _time
    from unittest.mock import patch

    db_path = tmp_path / "test.duckdb"
    _create_test_db(db_path, n=3)

    api = DashboardAPI(db_path, proxy_port=19999)

    # Simulate: proxy was reachable, then failed 61 seconds ago
    api._proxy_url_cache = "http://127.0.0.1:19999"
    api._proxy_url_cache_time = _time.monotonic() - 100
    api._proxy_last_fail_time = _time.monotonic() - 61

    # Health check still fails
    with patch("otel_agent.dashboard.api.urllib.request.urlopen", side_effect=TimeoutError("busy")):
        result = api._proxy_url()
        assert result is None, "Should return None after 60s of proxy being unreachable"

    api.close()


def test_proxy_url_fresh_check_resets_cache(tmp_path):
    """Successful health check resets the failure timer.

    BUG-002: If the proxy comes back after a brief outage, the cache should
    be refreshed and the failure timer reset.
    """
    import time as _time
    from unittest.mock import patch, MagicMock

    db_path = tmp_path / "test.duckdb"
    _create_test_db(db_path, n=3)

    api = DashboardAPI(db_path, proxy_port=19999)

    # Simulate: proxy was reachable, then failed for 30s
    api._proxy_url_cache = "http://127.0.0.1:19999"
    api._proxy_url_cache_time = _time.monotonic() - 100
    api._proxy_last_fail_time = _time.monotonic() - 30

    # Health check succeeds (proxy came back)
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("otel_agent.dashboard.api.urllib.request.urlopen", return_value=mock_resp):
        result = api._proxy_url()
        assert result == "http://127.0.0.1:19999"
        assert api._proxy_last_fail_time == 0.0, "Failure timer should be reset"

    api.close()

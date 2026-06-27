"""Tests for dashboard API and server."""

import json
import sqlite3
import tempfile
from pathlib import Path

from otel_agent.dashboard.api import DashboardAPI


def _create_test_db(db_path: Path, n: int = 5) -> None:
    """Create a test database with n requests."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
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
    conn.commit()
    conn.close()


def test_get_requests_empty(tmp_path):
    db = tmp_path / "test.db"
    api = DashboardAPI(db)
    result = api.get_requests()
    assert result == {"data": [], "total": 0, "page": 1, "per_page": 50}


def test_get_requests_with_data(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    result = api.get_requests()
    assert result["total"] == 5
    assert len(result["data"]) == 5
    assert result["page"] == 1
    assert result["per_page"] == 50


def test_get_requests_pagination(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db, 10)
    api = DashboardAPI(db)
    result = api.get_requests(page=1, per_page=3)
    assert result["total"] == 10
    assert len(result["data"]) == 3
    assert result["page"] == 1

    result2 = api.get_requests(page=2, per_page=3)
    assert len(result2["data"]) == 3
    # Different page = different rows
    assert result["data"][0]["id"] != result2["data"][0]["id"]


def test_get_requests_search(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    result = api.get_requests(search="completions/3")
    assert result["total"] == 1
    assert result["data"][0]["url"] == "/openai/v1/chat/completions/3"


def test_get_requests_filter_method(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    result = api.get_requests(method="POST")
    # POST = odd ids (1, 3, 5)
    assert result["total"] == 3
    for r in result["data"]:
        assert r["method"] == "POST"


def test_get_requests_filter_status(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    result = api.get_requests(status=500)
    # 500 = ids 4, 5
    assert result["total"] == 2
    for r in result["data"]:
        assert r["response_status"] == 500


def test_get_request_detail(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db, 3)
    api = DashboardAPI(db)
    result = api.get_request(2)
    assert result is not None
    assert result["id"] == 2
    assert result["method"] == "GET"
    assert isinstance(result["request_headers"], dict)


def test_get_request_not_found(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db, 3)
    api = DashboardAPI(db)
    assert api.get_request(999) is None


def test_get_requests_since(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    result = api.get_requests_since(3)
    assert len(result) == 2
    assert all(r["id"] > 3 for r in result)


def test_get_max_id(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    assert api.get_max_id() == 5


def test_get_max_id_empty(tmp_path):
    db = tmp_path / "test.db"
    api = DashboardAPI(db)
    assert api.get_max_id() == 0


def test_get_all_filtered(tmp_path):
    db = tmp_path / "test.db"
    _create_test_db(db, 5)
    api = DashboardAPI(db)
    result = api.get_all_filtered(method="POST")
    assert len(result) == 3
    assert all(r["method"] == "POST" for r in result)

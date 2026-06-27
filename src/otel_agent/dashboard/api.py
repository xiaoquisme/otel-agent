"""Dashboard JSON API — reads from SQLite telemetry database."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


class CountCache:
    """Cache COUNT results with a TTL to avoid full table scans."""

    def __init__(self, ttl: float = 5.0):
        self.ttl = ttl
        self._cache: dict[str, tuple[int, float]] = {}

    def get(self, key: str, conn: sqlite3.Connection, query: str, params: list) -> int:
        now = time.monotonic()
        if key in self._cache:
            value, cached_at = self._cache[key]
            if now - cached_at < self.ttl:
                return value
        result = conn.execute(query, params).fetchone()[0]
        self._cache[key] = (result, now)
        return result

    def clear(self) -> None:
        self._cache.clear()


class DashboardAPI:
    """Query the requests table for the dashboard."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._count_cache = CountCache(ttl=5.0)

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create a persistent connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _build_where(self, search: str = "", method: str = "", status: int = 0) -> tuple[str, list]:
        conditions = []
        params: list = []
        # Apply indexed filters first for query optimization
        if method:
            conditions.append("method = ?")
            params.append(method)
        if status:
            conditions.append("response_status = ?")
            params.append(status)
        if search:
            conditions.append("(url LIKE ? OR upstream LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        where = " AND ".join(conditions) if conditions else "1=1"
        return where, params

    def get_requests(self, search: str = "", method: str = "", status: int = 0,
                     cursor: int = 0, limit: int = 50) -> dict:
        """Get paginated requests using cursor-based pagination."""
        if not self.db_path.exists():
            return {"data": [], "total": 0, "cursor": cursor, "next_cursor": 0, "has_more": False}

        conn = self._get_conn()
        where, params = self._build_where(search, method, status)

        # Cached COUNT
        count_query = f"SELECT COUNT(*) FROM requests WHERE {where}"
        count_key = f"{where}|{params}"
        total = self._count_cache.get(count_key, conn, count_query, params)

        # Cursor-based pagination
        if cursor > 0:
            cursor_where = f"({where}) AND id < ?"
            cursor_params = params + [cursor]
        else:
            cursor_where = where
            cursor_params = params

        rows = conn.execute(
            f"SELECT id, timestamp, method, url, upstream, response_status, latency_ms "
            f"FROM requests WHERE {cursor_where} ORDER BY id DESC LIMIT ?",
            cursor_params + [limit + 1],
        ).fetchall()

        has_more = len(rows) > limit
        data = [dict(r) for r in rows[:limit]]
        next_cursor = data[-1]["id"] if data and has_more else 0

        return {
            "data": data,
            "total": total,
            "cursor": cursor,
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    def get_request(self, request_id: int) -> dict | None:
        """Get full details for a single request."""
        if not self.db_path.exists():
            return None

        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        for field in ("request_headers", "response_headers"):
            if result.get(field):
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    pass
        return result

    def get_requests_since(self, last_id: int) -> list[dict]:
        """Get requests with id > last_id (for SSE)."""
        if not self.db_path.exists():
            return []

        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, timestamp, method, url, upstream, response_status, latency_ms "
            "FROM requests WHERE id > ? ORDER BY id ASC",
            (last_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_max_id(self) -> int:
        """Get the current max request id."""
        if not self.db_path.exists():
            return 0

        conn = self._get_conn()
        row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM requests").fetchone()
        return row[0]

    def get_all_filtered(self, search: str = "", method: str = "", status: int = 0) -> list[dict]:
        """Get all filtered requests (for export, no pagination)."""
        if not self.db_path.exists():
            return []

        where, params = self._build_where(search, method, status)
        conn = self._get_conn()
        rows = conn.execute(
            f"SELECT * FROM requests WHERE {where} ORDER BY id DESC", params
        ).fetchall()
        return [dict(r) for r in rows]

    def clear_cache(self) -> None:
        """Clear the COUNT cache."""
        self._count_cache.clear()

    def close(self) -> None:
        """Close the persistent connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

"""Dashboard JSON API — reads from DuckDB telemetry database.

When the proxy is running, queries are routed through the proxy's internal
API to avoid DuckDB multi-process lock conflicts (BUG-001). Falls back to
direct DuckDB connection when the proxy is not running (offline/CLI use).
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Any

from otel_agent.db_compat import get_connection, rows_to_dicts


class CountCache:
    """Cache COUNT results with a TTL to avoid full table scans."""

    def __init__(self, ttl: float = 5.0):
        self.ttl = ttl
        self._cache: dict[str, tuple[int, float]] = {}

    def get(self, key: str, conn, query: str, params: list) -> int:
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
    """Query the requests table for the dashboard.

    Supports two modes:
    - Proxy mode: routes queries through the proxy's internal HTTP API
      (avoids DuckDB multi-process lock conflict).
    - Direct mode: opens a read-only DuckDB connection directly
      (used when proxy is not running, e.g. offline CLI use).
    """

    def __init__(self, db_path: Path, proxy_port: int | None = None):
        self.db_path = db_path
        self._conn = None
        self._count_cache = CountCache(ttl=5.0)
        self._proxy_port = proxy_port
        # BUG-002: Cache proxy URL to avoid health-check race condition
        self._proxy_url_cache: str | None = None
        self._proxy_url_cache_time: float = 0.0
        self._proxy_last_fail_time: float = 0.0

    def _proxy_url(self) -> str | None:
        """Return the proxy base URL if the proxy is reachable, else None.

        BUG-002 fix: Caches the proxy URL with a 30s TTL. If the proxy was
        previously reachable, keeps using it even if a single health check
        fails (avoids race condition where busy proxy causes timeout → fallback
        to direct DuckDB → lock conflict). Only falls back to direct DuckDB
        if the proxy has been unreachable for > 60s.
        """
        if self._proxy_port is None:
            return None

        now = time.monotonic()
        url = f"http://127.0.0.1:{self._proxy_port}"

        # Return cached result if within TTL (30s)
        if self._proxy_url_cache is not None and now - self._proxy_url_cache_time < 30:
            return self._proxy_url_cache

        # Do a live health check
        try:
            req = urllib.request.Request(f"{url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    self._proxy_url_cache = url
                    self._proxy_url_cache_time = now
                    self._proxy_last_fail_time = 0.0
                    return url
        except (urllib.error.URLError, OSError, TimeoutError):
            pass

        # Health check failed. If proxy was previously reachable, keep using it
        # for up to 60s to avoid lock conflict from fallback to direct DuckDB.
        if self._proxy_url_cache is not None:
            if self._proxy_last_fail_time == 0.0:
                self._proxy_last_fail_time = now
            if now - self._proxy_last_fail_time < 60:
                return self._proxy_url_cache
            # Been unreachable for > 60s — clear cache, fall back to direct
            self._proxy_url_cache = None
            self._proxy_url_cache_time = 0.0
            self._proxy_last_fail_time = 0.0

        return None

    def _get_conn(self):
        """Get or create a persistent direct DuckDB connection."""
        if self._conn is None:
            self._conn = get_connection(self.db_path, read_only=True)
        return self._conn

    def _build_where(self, search: str = "", method: str = "", status: int = 0) -> tuple[str, list]:
        conditions = []
        params: list = []
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

    def _http_get(self, path: str, params: dict | None = None) -> Any:
        """Make a GET request to the proxy's internal API. Returns parsed JSON or None."""
        base = self._proxy_url()
        if base is None:
            return None
        url = f"{base}{path}"
        if params:
            qs = urllib.parse.urlencode({k: v for k, v in params.items() if v})
            url = f"{url}?{qs}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return None

    def get_requests(self, search: str = "", method: str = "", status: int = 0,
                     cursor: int = 0, limit: int = 50) -> dict:
        """Get paginated requests using cursor-based pagination."""
        if not self.db_path.exists():
            return {"data": [], "total": 0, "cursor": cursor, "next_cursor": 0, "has_more": False}

        # Try proxy first (BUG-001 fix)
        proxy_result = self._http_get("/internal/dashboard/requests", {
            "search": search, "method": method, "status": status,
            "cursor": cursor, "limit": limit,
        })
        if proxy_result is not None:
            return proxy_result

        # Fallback: direct DuckDB connection
        conn = self._get_conn()
        where, params = self._build_where(search, method, status)

        count_query = f"SELECT COUNT(*) FROM requests WHERE {where}"
        count_key = f"{where}|{params}"
        total = self._count_cache.get(count_key, conn, count_query, params)

        if cursor > 0:
            cursor_where = f"({where}) AND id < ?"
            cursor_params = params + [cursor]
        else:
            cursor_where = where
            cursor_params = params

        result = conn.execute(
            f"SELECT id, timestamp, method, url, upstream, response_status, latency_ms "
            f"FROM requests WHERE {cursor_where} ORDER BY id DESC LIMIT ?",
            cursor_params + [limit + 1],
        )
        rows = result.fetchall()
        columns = [desc[0] for desc in result.description] if result.description else []
        data = [dict(zip(columns, r)) for r in rows[:limit]]

        has_more = len(rows) > limit
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

        # Try proxy first (BUG-001 fix)
        proxy_result = self._http_get(f"/internal/dashboard/requests/{request_id}")
        if proxy_result is not None:
            return proxy_result

        # Fallback: direct DuckDB connection
        conn = self._get_conn()
        result = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)
        )
        row = result.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in result.description] if result.description else []
        result_dict = dict(zip(columns, row))
        for field in ("request_headers", "response_headers"):
            if result_dict.get(field):
                try:
                    result_dict[field] = json.loads(result_dict[field])
                except json.JSONDecodeError:
                    pass
        return result_dict

    def get_requests_since(self, last_id: int) -> list[dict]:
        """Get requests with id > last_id (for SSE)."""
        if not self.db_path.exists():
            return []

        # Try proxy first (BUG-001 fix)
        proxy_result = self._http_get(f"/internal/dashboard/requests-since/{last_id}")
        if proxy_result is not None:
            return proxy_result

        # Fallback: direct DuckDB connection
        conn = self._get_conn()
        result = conn.execute(
            "SELECT id, timestamp, method, url, upstream, response_status, latency_ms "
            "FROM requests WHERE id > ? ORDER BY id ASC",
            (last_id,),
        )
        rows = result.fetchall()
        columns = [desc[0] for desc in result.description] if result.description else []
        return [dict(zip(columns, r)) for r in rows]

    def get_max_id(self) -> int:
        """Get the current max request id."""
        if not self.db_path.exists():
            return 0

        # Try proxy first (BUG-001 fix)
        proxy_result = self._http_get("/internal/dashboard/max-id")
        if proxy_result is not None:
            return proxy_result

        # Fallback: direct DuckDB connection
        conn = self._get_conn()
        row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM requests").fetchone()
        return row[0]

    def get_all_filtered(self, search: str = "", method: str = "", status: int = 0) -> list[dict]:
        """Get all filtered requests (for export, no pagination)."""
        if not self.db_path.exists():
            return []

        # Try proxy first (BUG-001 fix)
        proxy_result = self._http_get("/internal/dashboard/export", {
            "search": search, "method": method, "status": status,
        })
        if proxy_result is not None:
            return proxy_result

        # Fallback: direct DuckDB connection
        where, params = self._build_where(search, method, status)
        conn = self._get_conn()
        result = conn.execute(
            f"SELECT * FROM requests WHERE {where} ORDER BY id DESC", params
        )
        rows = result.fetchall()
        columns = [desc[0] for desc in result.description] if result.description else []
        return [dict(zip(columns, r)) for r in rows]

    def clear_cache(self) -> None:
        """Clear the COUNT cache."""
        self._count_cache.clear()

    def close(self) -> None:
        """Close the persistent connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

"""Dashboard JSON API — reads from the storage backend directly.

The dashboard now runs in the same process as the FastAPI proxy, so there
is no need for proxy-fallback logic or multi-process lock workarounds.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from otel_agent.dashboard.render import render_request_body, render_response_body
from otel_agent.storage import create_storage


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

    Now that the dashboard runs inside the same process as the proxy,
    all queries go directly to the storage backend (no HTTP proxy loop).
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._storage = create_storage("duckdb", db_path, read_only=True)
        self._count_cache = CountCache(ttl=5.0)

    def get_requests(self, search: str = "", method: str = "", status: int = 0,
                     cursor: int = 0, limit: int = 50) -> dict:
        """Get paginated requests using cursor-based pagination."""
        if not self.db_path.exists():
            return {"data": [], "total": 0, "cursor": cursor, "next_cursor": 0, "has_more": False}
        return self._storage.get_requests(search, method, status, cursor, limit)

    def get_request(self, request_id: int) -> dict | None:
        """Get full details for a single request."""
        if not self.db_path.exists():
            return None
        return self._storage.get_request(request_id)

    def get_requests_since(self, last_id: int) -> list[dict]:
        """Get requests with id > last_id (for SSE)."""
        if not self.db_path.exists():
            return []
        return self._storage.get_requests_since(last_id)

    def get_max_id(self) -> int:
        """Get the current max request id."""
        if not self.db_path.exists():
            return 0
        return self._storage.get_max_id()

    def get_all_filtered(self, search: str = "", method: str = "", status: int = 0) -> list[dict]:
        """Get all filtered requests (for export, no pagination)."""
        if not self.db_path.exists():
            return []
        return self._storage.get_all_filtered(search, method, status)

    def get_usage_summary(self, start: str, end: str) -> dict:
        """Return usage summary for the requested UTC range."""
        if not self.db_path.exists():
            return {"start": start, "end": end, "total_tokens": 0, "input_tokens": 0,
                    "output_tokens": 0, "eligible_request_count": 0, "excluded_request_count": 0, "models": []}
        return self._storage.get_usage_summary(start, end)

    def get_rendered_request(self, request_id: int) -> dict | None:
        """Get a request with pre-rendered HTML for LLM bodies."""
        result = self.get_request(request_id)
        if result is None:
            return None
        fmt = result.get("format")
        req_body = result.get("request_body") or ""
        resp_body = result.get("response_body") or ""
        result["rendered_request"] = render_request_body(req_body, fmt)
        result["rendered_response"] = render_response_body(resp_body, fmt)
        return result

    def clear_cache(self) -> None:
        """Clear the COUNT cache."""
        self._count_cache.clear()

    def close(self) -> None:
        """Close the persistent connection."""
        if self._storage is not None:
            self._storage.close()

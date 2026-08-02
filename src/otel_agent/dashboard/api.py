"""Dashboard JSON API — reads from the storage backend.

When proxy_port is set, queries route through the proxy's internal HTTP API.
Falls back to direct database access when the proxy is unreachable.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from otel_agent.dashboard.message_parser import parse_messages
from otel_agent.storage import create_storage
from otel_agent.storage.base import StorageBackend


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

    When *proxy_port* is provided, queries are routed through the proxy's
    internal HTTP API.  Falls back to direct database access when the
    proxy is unreachable.

    When *storage* is provided (e.g., from the proxy's TelemetryLogger),
    uses that storage backend directly instead of opening a new connection.
    """

    def __init__(self, db_path: Path, proxy_port: int | None = None,
                 storage: StorageBackend | None = None):
        self.db_path = db_path
        self._proxy_port = proxy_port
        self._proxy_url_cache: str | None = None
        self._proxy_url_cache_time: float = 0
        self._storage = storage
        self._owns_storage = storage is None  # Only close if we created it
        self._count_cache = CountCache(ttl=5.0)

    # ------------------------------------------------------------------
    # Proxy routing helpers
    # ------------------------------------------------------------------

    def _proxy_url(self) -> str | None:
        """Return cached proxy base URL if reachable, else None."""
        if self._proxy_port is None:
            return None

        now = time.monotonic()
        # Use cached URL if fresh (< 30s)
        if self._proxy_url_cache is not None and now - self._proxy_url_cache_time < 30:
            return self._proxy_url_cache

        import httpx
        url = f"http://127.0.0.1:{self._proxy_port}"
        try:
            r = httpx.get(f"{url}/health", timeout=2.0, trust_env=False)
            if r.status_code == 200:
                self._proxy_url_cache = url
                self._proxy_url_cache_time = now
                return url
        except Exception:
            pass

        # If previously cached, keep using it for up to 60s
        if self._proxy_url_cache is not None and now - self._proxy_url_cache_time < 60:
            return self._proxy_url_cache
        return None

    def _http_get(self, path: str, params: dict | None = None) -> Any:
        """Fetch JSON from the proxy's internal API. Returns None on failure."""
        base = self._proxy_url()
        if base is None:
            return None
        import httpx
        try:
            r = httpx.get(f"{base}{path}", params=params, timeout=5.0, trust_env=False)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def _get_storage(self):
        """Return (and lazily create) the storage connection."""
        if self._storage is None:
            self._storage = create_storage("sqlite", self.db_path, read_only=True)
            self._owns_storage = True
        return self._storage

    def _empty_requests(self, cursor: int = 0) -> dict:
        """Return an empty requests response."""
        return {"data": [], "total": 0, "cursor": cursor, "next_cursor": 0, "has_more": False}

    def _empty_usage(self, start: str, end: str) -> dict:
        """Return an empty usage response."""
        return {"start": start, "end": end, "total_tokens": 0, "input_tokens": 0,
                "output_tokens": 0, "eligible_request_count": 0, "excluded_request_count": 0, "models": []}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_requests(self, search: str = "", method: str = "", status: int = 0,
                     cursor: int = 0, limit: int = 50) -> dict:
        """Get paginated requests using cursor-based pagination."""
        params = {"search": search, "method": method, "status": status, "cursor": cursor, "limit": limit}
        result = self._http_get("/api/requests", params)
        if result is not None:
            return result

        # If proxy_port was specified, the proxy should be handling DB access.
        # Don't fall back to direct DB (would cause lock conflict).
        if self._proxy_port is not None:
            return self._empty_requests(cursor)

        # No proxy — direct DB access (single-process mode)
        if not self.db_path.exists():
            return self._empty_requests(cursor)
        return self._get_storage().get_requests(search, method, status, cursor, limit)

    def get_request(self, request_id: int) -> dict | None:
        """Get full details for a single request."""
        result = self._http_get(f"/api/requests/{request_id}")
        if result is not None:
            return result

        if self._proxy_port is not None:
            return None

        if not self.db_path.exists():
            return None
        return self._get_storage().get_request(request_id)

    def get_all_filtered(self, search: str = "", method: str = "", status: int = 0) -> list[dict]:
        """Get all filtered requests (for export, no pagination)."""
        result = self._http_get("/api/export", {"format": "json", "search": search, "method": method, "status": status})
        if result is not None:
            return result if isinstance(result, list) else []

        if self._proxy_port is not None:
            return []

        if not self.db_path.exists():
            return []
        return self._get_storage().get_all_filtered(search, method, status)

    def get_usage_summary(self, start: str, end: str) -> dict:
        """Return usage summary for the requested UTC range."""
        result = self._http_get("/api/usage", {"start": start, "end": end})
        if result is not None:
            return result

        if self._proxy_port is not None:
            return self._empty_usage(start, end)

        if not self.db_path.exists():
            return self._empty_usage(start, end)
        return self._get_storage().get_usage_summary(start, end)

    def get_structured_request(self, request_id: int) -> dict | None:
        """Get a request with parsed structured messages for frontend rendering."""
        result = self.get_request(request_id)
        if result is None:
            return None
        fmt = result.get("format")
        req_body = result.get("request_body") or ""
        resp_body = result.get("response_body") or ""
        parsed = parse_messages(req_body, resp_body, fmt)
        result["messages"] = parsed["messages"]
        result["metadata"] = parsed["metadata"]
        return result

    def clear_cache(self) -> None:
        """Clear the COUNT cache."""
        self._count_cache.clear()

    def close(self) -> None:
        """Close the persistent connection (only if we created it)."""
        if self._owns_storage and self._storage is not None:
            self._storage.close()
            self._storage = None

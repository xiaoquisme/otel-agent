"""Dashboard JSON API — reads from the storage backend.

When the proxy is running, queries are routed through the proxy's internal
API to avoid DuckDB multi-process lock conflicts (BUG-001). Falls back to
direct storage connection when the proxy is not running (offline/CLI use).
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Any

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

    Supports two modes:
    - Proxy mode: routes queries through the proxy's internal HTTP API
      (avoids DuckDB multi-process lock conflict).
    - Direct mode: opens a read-only storage connection directly
      (used when proxy is not running, e.g. offline CLI use).
    """

    def __init__(self, db_path: Path, proxy_port: int | None = None):
        self.db_path = db_path
        self._storage = create_storage("duckdb", db_path, read_only=True)
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

        # Fallback: direct storage connection
        return self._storage.get_requests(search, method, status, cursor, limit)

    def get_request(self, request_id: int) -> dict | None:
        """Get full details for a single request."""
        if not self.db_path.exists():
            return None

        # Try proxy first (BUG-001 fix)
        proxy_result = self._http_get(f"/internal/dashboard/requests/{request_id}")
        if proxy_result is not None:
            return proxy_result

        # Fallback: direct storage connection
        return self._storage.get_request(request_id)

    def get_requests_since(self, last_id: int) -> list[dict]:
        """Get requests with id > last_id (for SSE)."""
        if not self.db_path.exists():
            return []

        # Try proxy first (BUG-001 fix)
        proxy_result = self._http_get(f"/internal/dashboard/requests-since/{last_id}")
        if proxy_result is not None:
            return proxy_result

        # Fallback: direct storage connection
        return self._storage.get_requests_since(last_id)

    def get_max_id(self) -> int:
        """Get the current max request id."""
        if not self.db_path.exists():
            return 0

        # Try proxy first (BUG-001 fix)
        proxy_result = self._http_get("/internal/dashboard/max-id")
        if proxy_result is not None:
            return proxy_result

        # Fallback: direct storage connection
        return self._storage.get_max_id()

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

        # Fallback: direct storage connection
        return self._storage.get_all_filtered(search, method, status)

    def get_usage_summary(self, start: str, end: str) -> dict:
        """Return proxy-safe usage summary for the requested UTC range."""
        proxy_result = self._http_get("/internal/dashboard/usage", {"start": start, "end": end})
        if proxy_result is not None:
            return proxy_result
        if not self.db_path.exists():
            return {"start": start, "end": end, "total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "eligible_request_count": 0, "excluded_request_count": 0, "models": []}
        return self._storage.get_usage_summary(start, end)

    def clear_cache(self) -> None:
        """Clear the COUNT cache."""
        self._count_cache.clear()

    def close(self) -> None:
        """Close the persistent connection."""
        if self._storage is not None:
            self._storage.close()

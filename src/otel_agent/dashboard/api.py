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

    def _empty_sessions(self, offset: int = 0, limit: int = 50) -> dict:
        """Return an empty session list."""
        return {
            "data": [],
            "total": 0,
            "offset": offset,
            "limit": limit,
            "has_more": False,
        }

    def _empty_usage(self, start: str, end: str) -> dict:
        """Return an empty usage response."""
        return {"start": start, "end": end, "total_tokens": 0, "input_tokens": 0,
                "output_tokens": 0, "cache_read_tokens": 0, "cache_creation_tokens": 0,
                "cacheable_input_tokens": 0, "cache_hit_rate": None,
                "eligible_request_count": 0, "excluded_request_count": 0, "models": []}

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

    def list_sessions(self, limit: int = 50, offset: int = 0) -> dict:
        """Recent agent sessions, newest activity first.

        Follows the same proxy-then-storage path as :meth:`get_requests`.
        """
        params = {"limit": limit, "offset": offset}
        result = self._http_get("/api/sessions", params)
        if result is not None:
            return result
        if self._proxy_port is not None or not self.db_path.exists():
            return self._empty_sessions(offset, limit)
        return self._get_storage().list_sessions(limit=limit, offset=offset)

    def get_session(self, session_id: str) -> dict | None:
        """One session trajectory, or None when that id was never logged."""
        from urllib.parse import quote

        result = self._http_get(f"/api/sessions/{quote(session_id, safe='')}")
        if result is not None:
            return result
        if self._proxy_port is not None or not self.db_path.exists():
            return None
        return self._get_storage().get_session(session_id)

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

    def get_usage_series(
        self,
        start: str,
        end: str,
        bucket: str | None = None,
        tz: str | None = None,
    ) -> dict:
        """Return bucketed token totals for the requested UTC range.

        Follows the same proxy-then-storage path as :meth:`get_usage_summary`.
        """
        params: dict[str, str] = {"start": start, "end": end}
        if bucket:
            params["bucket"] = bucket
        if tz:
            params["tz"] = tz
        result = self._http_get("/api/usage/series", params)
        if result is not None:
            return result

        if self._proxy_port is not None or not self.db_path.exists():
            return self._empty_usage_series(start, end, bucket, tz)
        return self._get_storage().get_usage_series(start, end, bucket, tz)

    def _empty_usage_series(
        self,
        start: str,
        end: str,
        bucket: str | None,
        tz: str | None,
    ) -> dict:
        """Zero-filled series when the database cannot be read."""
        from datetime import datetime, timezone

        from otel_agent.usage_series import (
            build_usage_series,
            resolve_timezone,
            select_bucket,
        )

        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            zone = resolve_timezone(tz)
            now = datetime.now(timezone.utc)
            chosen = select_bucket(start_dt, end_dt, bucket, zone, now)
        except (ValueError, TypeError, AttributeError):
            return {
                "start": start, "end": end, "bucket": "hour",
                "timezone": "UTC", "points": [],
            }
        return build_usage_series(
            start, end, start_dt, end_dt, chosen, [], zone, now=now,
        )

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

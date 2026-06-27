"""Dashboard JSON API — reads from SQLite telemetry database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class DashboardAPI:
    """Query the requests table for the dashboard."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _build_where(self, search: str = "", method: str = "", status: int = 0) -> tuple[str, list]:
        conditions = []
        params: list = []
        if search:
            conditions.append("(url LIKE ? OR upstream LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        if method:
            conditions.append("method = ?")
            params.append(method)
        if status:
            conditions.append("response_status = ?")
            params.append(status)
        where = " AND ".join(conditions) if conditions else "1=1"
        return where, params

    def get_requests(self, search: str = "", method: str = "", status: int = 0,
                     page: int = 1, per_page: int = 50) -> dict:
        """Get paginated, filtered requests."""
        if not self.db_path.exists():
            return {"data": [], "total": 0, "page": page, "per_page": per_page}

        where, params = self._build_where(search, method, status)
        offset = (page - 1) * per_page

        conn = self._connect()
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM requests WHERE {where}", params
            ).fetchone()[0]

            rows = conn.execute(
                f"SELECT id, timestamp, method, url, upstream, response_status, latency_ms "
                f"FROM requests WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                params + [per_page, offset],
            ).fetchall()

            data = [dict(r) for r in rows]
            return {"data": data, "total": total, "page": page, "per_page": per_page}
        finally:
            conn.close()

    def get_request(self, request_id: int) -> dict | None:
        """Get full details for a single request."""
        if not self.db_path.exists():
            return None

        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM requests WHERE id = ?", (request_id,)
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            # Parse JSON fields
            for field in ("request_headers", "response_headers"):
                if result.get(field):
                    try:
                        result[field] = json.loads(result[field])
                    except json.JSONDecodeError:
                        pass
            return result
        finally:
            conn.close()

    def get_requests_since(self, last_id: int) -> list[dict]:
        """Get requests with id > last_id (for SSE)."""
        if not self.db_path.exists():
            return []

        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, timestamp, method, url, upstream, response_status, latency_ms "
                "FROM requests WHERE id > ? ORDER BY id ASC",
                (last_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_max_id(self) -> int:
        """Get the current max request id."""
        if not self.db_path.exists():
            return 0

        conn = self._connect()
        try:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM requests").fetchone()
            return row[0]
        finally:
            conn.close()

    def get_all_filtered(self, search: str = "", method: str = "", status: int = 0) -> list[dict]:
        """Get all filtered requests (for export, no pagination)."""
        if not self.db_path.exists():
            return []

        where, params = self._build_where(search, method, status)
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM requests WHERE {where} ORDER BY id DESC", params
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

"""DuckDB storage backend."""

from __future__ import annotations

import json
from pathlib import Path

from otel_agent.storage.base import StorageBackend


class DuckDBStorage(StorageBackend):
    """Backend backed by DuckDB."""

    def __init__(self, db_path: Path, read_only: bool = False) -> None:
        self.db_path = db_path
        self.read_only = read_only
        self._conn = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self):
        """Return (and lazily create) the DuckDB connection."""
        if self._conn is None:
            import duckdb

            self._conn = duckdb.connect(str(self.db_path), read_only=self.read_only)
        return self._conn

    # ------------------------------------------------------------------
    # StorageBackend interface
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        conn = self._get_conn()
        conn.execute("CREATE SEQUENCE IF NOT EXISTS requests_id_seq START 1")
        conn.execute(
            """
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
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_method ON requests(method)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(response_status)"
        )
        for column in ("model_name TEXT", "input_tokens BIGINT", "output_tokens BIGINT", "total_tokens BIGINT"):
            conn.execute(f"ALTER TABLE requests ADD COLUMN IF NOT EXISTS {column}")
        conn.commit()

    def log_request(
        self,
        method: str,
        url: str,
        request_headers: dict,
        request_body: str,
        response_status: int,
        response_headers: dict,
        response_body: str,
        latency_ms: float,
        upstream: str = "", model_name: str | None = None,
        input_tokens: int | None = None, output_tokens: int | None = None,
        total_tokens: int | None = None, timestamp: str | None = None,
    ) -> None:
        from datetime import datetime, timezone

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO requests
               (timestamp, method, url, upstream, request_headers, request_body,
                response_status, response_headers, response_body, latency_ms, model_name,
                input_tokens, output_tokens, total_tokens)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                timestamp or datetime.now(timezone.utc).isoformat(),
                method,
                url,
                upstream,
                json.dumps(request_headers),
                request_body,
                response_status,
                json.dumps(response_headers),
                response_body,
                latency_ms, model_name, input_tokens, output_tokens, total_tokens,
            ),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_where(
        search: str = "", method: str = "", status: int = 0
    ) -> tuple[str, list]:
        conditions: list[str] = []
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

    def get_requests(
        self,
        search: str = "",
        method: str = "",
        status: int = 0,
        cursor: int = 0,
        limit: int = 50,
    ) -> dict:
        conn = self._get_conn()
        where, params = self._build_where(search, method, status)

        total = conn.execute(
            f"SELECT COUNT(*) FROM requests WHERE {where}", params
        ).fetchone()[0]

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
        conn = self._get_conn()
        row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM requests").fetchone()
        return row[0]

    def get_all_filtered(
        self, search: str = "", method: str = "", status: int = 0
    ) -> list[dict]:
        conn = self._get_conn()
        where, params = self._build_where(search, method, status)
        result = conn.execute(
            f"SELECT * FROM requests WHERE {where} ORDER BY id DESC", params
        )
        rows = result.fetchall()
        columns = [desc[0] for desc in result.description] if result.description else []
        return [dict(zip(columns, r)) for r in rows]

    def get_usage_summary(self, start: str, end: str) -> dict:
        """Aggregate completed request usage in a UTC half-open range."""
        conn = self._get_conn()
        where = "CAST(timestamp AS TIMESTAMPTZ) >= CAST(? AS TIMESTAMPTZ) AND CAST(timestamp AS TIMESTAMPTZ) < CAST(? AS TIMESTAMPTZ) AND response_status BETWEEN 200 AND 299"
        totals = conn.execute(f"SELECT COALESCE(SUM(total_tokens), 0), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0), COUNT(total_tokens), COUNT(*) - COUNT(total_tokens) FROM requests WHERE {where}", [start, end]).fetchone()
        rows = conn.execute(f"SELECT model_name, COALESCE(SUM(total_tokens), 0), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0), COUNT(*) FROM requests WHERE {where} AND total_tokens IS NOT NULL GROUP BY model_name ORDER BY 2 DESC, model_name ASC", [start, end]).fetchall()
        return {"start": start, "end": end, "total_tokens": totals[0], "input_tokens": totals[1], "output_tokens": totals[2], "eligible_request_count": totals[3], "excluded_request_count": totals[4], "models": [{"model_name": row[0], "total_tokens": row[1], "input_tokens": row[2], "output_tokens": row[3], "request_count": row[4]} for row in rows]}

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

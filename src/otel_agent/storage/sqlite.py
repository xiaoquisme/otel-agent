"""SQLite storage backend (stdlib sqlite3)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from otel_agent.storage.base import StorageBackend


def _hit_rate(cache_read: int, cacheable_input: int) -> float | None:
    """Cache hit rate as a 0-1 ratio, or None when nothing was cacheable."""
    return round(cache_read / cacheable_input, 4) if cacheable_input else None


class SQLiteStorage(StorageBackend):
    """Backend backed by SQLite 3 via the stdlib :mod:`sqlite3` module.

    Uses ``INTEGER PRIMARY KEY AUTOINCREMENT`` instead of sequences and
    enables WAL journal mode for better concurrent-read performance.
    """

    def __init__(self, db_path: Path, read_only: bool = False) -> None:
        self.db_path = db_path
        self.read_only = read_only
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Return (and lazily create) the SQLite connection."""
        if self._conn is None:
            uri = f"file:{self.db_path}"
            if self.read_only:
                uri += "?mode=ro"
            self._conn = sqlite3.connect(
                uri if self.read_only else str(self.db_path),
                uri=self.read_only,
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            if not self.read_only:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA busy_timeout=5000")
                self._conn.execute("PRAGMA synchronous=NORMAL")
                self._conn.execute("PRAGMA wal_autocheckpoint=1000")
                self._conn.execute("PRAGMA cache_size=-64000")
        return self._conn

    # ------------------------------------------------------------------
    # StorageBackend interface
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        conn = self._get_conn()
        conn.execute(
            """
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
        for column in ("model_name TEXT", "input_tokens INTEGER", "output_tokens INTEGER", "total_tokens INTEGER", "cache_read_tokens INTEGER", "cache_creation_tokens INTEGER", "format TEXT"):
            try:
                conn.execute(f"ALTER TABLE requests ADD COLUMN {column}")
            except sqlite3.OperationalError:
                pass
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
        cache_read_tokens: int | None = None, cache_creation_tokens: int | None = None,
        format: str | None = None,
    ) -> None:
        from datetime import datetime, timezone

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO requests
               (timestamp, method, url, upstream, request_headers, request_body,
                response_status, response_headers, response_body, latency_ms, model_name,
                input_tokens, output_tokens, total_tokens, cache_read_tokens, cache_creation_tokens, format)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                cache_read_tokens, cache_creation_tokens, format,
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

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

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

        cur = conn.execute(
            f"SELECT id, timestamp, method, url, upstream, response_status, latency_ms, model_name "
            f"FROM requests WHERE {cursor_where} ORDER BY id DESC LIMIT ?",
            cursor_params + [limit + 1],
        )
        rows = cur.fetchall()
        data = [self._row_to_dict(r) for r in rows[:limit]]

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
        cur = conn.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        result_dict = self._row_to_dict(row)
        for field in ("request_headers", "response_headers"):
            if result_dict.get(field):
                try:
                    result_dict[field] = json.loads(result_dict[field])
                except json.JSONDecodeError:
                    pass
        return result_dict

    def get_all_filtered(
        self, search: str = "", method: str = "", status: int = 0
    ) -> list[dict]:
        conn = self._get_conn()
        where, params = self._build_where(search, method, status)
        cur = conn.execute(
            f"SELECT * FROM requests WHERE {where} ORDER BY id DESC", params
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def get_usage_summary(self, start: str, end: str) -> dict:
        """Aggregate completed request usage in a UTC half-open range.

        Cache accounting is dialect-normalized at write time (see
        ``normalize_cache_usage``): ``cache_read_tokens`` is tokens served
        from the prompt cache, ``cache_creation_tokens`` tokens written to it
        (reported by Anthropic-style providers only). The cache hit rate is
        ``cache_read_tokens / cacheable_input_tokens`` where the denominator
        counts every input-side token the model processed; rows that report
        cache creation are Anthropic-style (their ``input_tokens`` excludes
        cache), while other rows report input that already includes cached
        tokens.
        """
        conn = self._get_conn()
        where = "timestamp >= ? AND timestamp < ? AND response_status BETWEEN 200 AND 299"
        cacheable = (
            "CASE WHEN cache_creation_tokens IS NOT NULL "
            "THEN COALESCE(input_tokens, 0) + COALESCE(cache_read_tokens, 0) + cache_creation_tokens "
            "ELSE COALESCE(input_tokens, 0) END"
        )
        agg = (
            "COALESCE(SUM(total_tokens), 0), COALESCE(SUM(input_tokens), 0), "
            "COALESCE(SUM(output_tokens), 0), COALESCE(SUM(cache_read_tokens), 0), "
            f"COALESCE(SUM(cache_creation_tokens), 0), COALESCE(SUM({cacheable}), 0)"
        )
        totals = conn.execute(
            f"SELECT {agg}, COUNT(total_tokens), COUNT(*) - COUNT(total_tokens) FROM requests WHERE {where}",
            (start, end),
        ).fetchone()
        rows = conn.execute(
            f"SELECT model_name, {agg}, COUNT(*) FROM requests WHERE {where} AND total_tokens IS NOT NULL "
            "GROUP BY model_name ORDER BY 2 DESC, model_name ASC",
            (start, end),
        ).fetchall()

        def model_row(row) -> dict:
            cacheable_total = row[6]
            return {
                "model_name": row[0], "total_tokens": row[1], "input_tokens": row[2],
                "output_tokens": row[3], "cache_read_tokens": row[4],
                "cache_creation_tokens": row[5], "cacheable_input_tokens": cacheable_total,
                "cache_hit_rate": _hit_rate(row[4], cacheable_total), "request_count": row[7],
            }

        return {
            "start": start, "end": end,
            "total_tokens": totals[0], "input_tokens": totals[1], "output_tokens": totals[2],
            "cache_read_tokens": totals[3], "cache_creation_tokens": totals[4],
            "cacheable_input_tokens": totals[5],
            "cache_hit_rate": _hit_rate(totals[3], totals[5]),
            "eligible_request_count": totals[6], "excluded_request_count": totals[7],
            "models": [model_row(row) for row in rows],
        }

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

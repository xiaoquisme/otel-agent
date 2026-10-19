"""SQLite storage backend (stdlib sqlite3)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from otel_agent.sessions import (
    MAX_SESSION_ID_LEN,
    MAX_SESSION_STEP_LEN,
    assemble_session,
    clean_session_label,
    session_summary_from_row,
)
from otel_agent.storage.base import StorageBackend
from otel_agent.usage_series import (
    build_usage_series,
    resolve_timezone,
    select_bucket,
)


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
        for column in (
            "model_name TEXT",
            "input_tokens INTEGER",
            "output_tokens INTEGER",
            "total_tokens INTEGER",
            "cache_read_tokens INTEGER",
            "cache_creation_tokens INTEGER",
            "format TEXT",
            "session_id TEXT",
            "session_step TEXT",
        ):
            try:
                conn.execute(f"ALTER TABLE requests ADD COLUMN {column}")
            except sqlite3.OperationalError:
                pass
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_requests_session_time
            ON requests (session_id, timestamp, id)
            WHERE session_id IS NOT NULL
            """
        )
        # Usage summary and series seek idx_requests_status for every 2xx
        # row, then read token columns stored after the request and response
        # bodies. Rows inside the range pull those overflow pages (tens of
        # seconds, cold, when the range covers most of the table). Timestamp
        # leads this index so the range is a seek; the other columns make
        # the aggregate covering.
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_requests_usage ON requests (
                timestamp,
                response_status,
                model_name,
                input_tokens,
                output_tokens,
                total_tokens,
                cache_read_tokens,
                cache_creation_tokens
            )
            """
        )
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
        session_id: str | None = None,
        session_step: str | None = None,
    ) -> None:
        from datetime import datetime, timezone

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO requests
               (timestamp, method, url, upstream, request_headers, request_body,
                response_status, response_headers, response_body, latency_ms, model_name,
                input_tokens, output_tokens, total_tokens, cache_read_tokens, cache_creation_tokens, format,
                session_id, session_step)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                clean_session_label(session_id, MAX_SESSION_ID_LEN),
                clean_session_label(session_step, MAX_SESSION_STEP_LEN),
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

    def get_usage_series(
        self,
        start: str,
        end: str,
        bucket: str | None = None,
        tz: str | None = None,
    ) -> dict:
        """Bucket completed-request tokens across ``[start, end)``.

        Rows are grouped by UTC minute in SQL, then folded into local
        hour, day, week, or month marks. The same status filter as
        :meth:`get_usage_summary` applies, so series totals match that
        summary for the same range.
        """
        from datetime import datetime, timezone

        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        zone = resolve_timezone(tz)
        now = datetime.now(timezone.utc)
        chosen = select_bucket(start_dt, end_dt, bucket, zone, now)
        conn = self._get_conn()
        where = "timestamp >= ? AND timestamp < ? AND response_status BETWEEN 200 AND 299"
        rows = conn.execute(
            "SELECT substr(timestamp, 1, 16), "
            "COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0), "
            "COALESCE(SUM(total_tokens), 0), COUNT(total_tokens) "
            f"FROM requests WHERE {where} GROUP BY 1",
            (start, end),
        ).fetchall()
        return build_usage_series(
            start, end, start_dt, end_dt, chosen, rows, zone, now=now,
        )

    def _column_names(self) -> set[str]:
        """Column names on ``requests``, or empty when the table is absent."""
        conn = self._get_conn()
        try:
            rows = conn.execute("PRAGMA table_info(requests)").fetchall()
        except sqlite3.OperationalError:
            return set()
        return {row[1] for row in rows}

    def list_sessions(self, limit: int = 50, offset: int = 0) -> dict:
        """Recent sessions ordered by last activity, then session id."""
        limit = max(int(limit), 0)
        offset = max(int(offset), 0)
        empty = {
            "data": [],
            "total": 0,
            "offset": offset,
            "limit": limit,
            "has_more": False,
        }
        if "session_id" not in self._column_names():
            return empty
        conn = self._get_conn()
        where = "session_id IS NOT NULL AND session_id != ''"
        total = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT session_id FROM requests WHERE {where} GROUP BY session_id)"
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT session_id,
                   COUNT(*) AS request_count,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COUNT(total_tokens) AS token_request_count,
                   MIN(timestamp) AS first_timestamp,
                   MAX(timestamp) AS last_timestamp,
                   SUM(CASE
                         WHEN response_status IS NULL
                           OR response_status < 200
                           OR response_status >= 400
                         THEN 1 ELSE 0 END) AS error_count,
                   COALESCE(SUM(latency_ms), 0) AS total_latency_ms,
                   GROUP_CONCAT(DISTINCT model_name) AS models,
                   GROUP_CONCAT(DISTINCT upstream) AS upstreams
            FROM requests
            WHERE {where}
            GROUP BY session_id
            ORDER BY last_timestamp DESC, session_id ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        data = [session_summary_from_row(self._row_to_dict(row)) for row in rows]
        return {
            "data": data,
            "total": int(total),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(data) < int(total),
        }

    def get_session(self, session_id: str) -> dict | None:
        """One session's requests in timestamp order, with running token totals."""
        cleaned = clean_session_label(session_id, MAX_SESSION_ID_LEN)
        if cleaned is None or "session_id" not in self._column_names():
            return None
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT id, timestamp, method, url, upstream, response_status, latency_ms,
                   model_name, input_tokens, output_tokens, total_tokens,
                   cache_read_tokens, cache_creation_tokens, format, session_step,
                   substr(request_body, 1, 240) AS request_preview,
                   length(request_body) AS request_bytes,
                   substr(request_body, -256) AS request_suffix
            FROM requests
            WHERE session_id = ?
            ORDER BY timestamp ASC, id ASC
            """,
            (cleaned,),
        ).fetchall()
        if not rows:
            return None
        return assemble_session(cleaned, [self._row_to_dict(row) for row in rows])

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

"""Telemetry logger — writes request records to DuckDB (or SQLite fallback)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from otel_agent.db_compat import get_connection
from otel_agent.migration import migrate_sqlite_to_duckdb, needs_migration

SENSITIVE_HEADERS = frozenset({"authorization", "x-api-key", "set-cookie"})


def redact_sensitive_headers(headers: dict[str, str]) -> dict[str, str]:
    """Redact sensitive header values, replacing them with ``[REDACTED]``."""
    return {
        k: "[REDACTED]" if k.lower() in SENSITIVE_HEADERS else v
        for k, v in headers.items()
    }


class TelemetryLogger:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Auto-migrate existing SQLite database to DuckDB
        if needs_migration(db_path):
            duckdb_path = db_path.with_suffix(".duckdb")
            if migrate_sqlite_to_duckdb(db_path, duckdb_path):
                self.db_path = duckdb_path

        self.conn = get_connection(self.db_path)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute(
            "CREATE SEQUENCE IF NOT EXISTS requests_id_seq START 1"
        )
        self.conn.execute("""
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
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_method ON requests(method)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(response_status)"
        )
        self.conn.commit()

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
        upstream: str = "",
    ):
        self.conn.execute(
            """INSERT INTO requests
               (timestamp, method, url, upstream, request_headers, request_body,
                response_status, response_headers, response_body, latency_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                method, url, upstream,
                json.dumps(request_headers),
                request_body,
                response_status,
                json.dumps(response_headers),
                response_body,
                latency_ms,
            ),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()

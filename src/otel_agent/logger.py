"""Telemetry logger — writes request records to the storage backend."""

from __future__ import annotations

from pathlib import Path

from otel_agent.migration import migrate_sqlite_to_duckdb, needs_migration
from otel_agent.storage import create_storage

SENSITIVE_HEADERS = frozenset({"authorization", "x-api-key", "set-cookie"})


def redact_sensitive_headers(headers: dict[str, str]) -> dict[str, str]:
    """Redact sensitive header values, replacing them with ``[REDACTED]``."""
    return {
        k: "[REDACTED]" if k.lower() in SENSITIVE_HEADERS else v
        for k, v in headers.items()
    }


class TelemetryLogger:
    def __init__(self, db_path: Path, backend: str = "duckdb"):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Auto-migrate existing SQLite database to DuckDB
        if needs_migration(db_path):
            duckdb_path = db_path.with_suffix(".duckdb")
            if migrate_sqlite_to_duckdb(db_path, duckdb_path):
                self.db_path = duckdb_path

        self.storage = create_storage(backend, self.db_path)
        self.storage.initialize()

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
        model_name: str | None = None, input_tokens: int | None = None,
        output_tokens: int | None = None, total_tokens: int | None = None,
        timestamp: str | None = None, format: str | None = None,
    ):
        self.storage.log_request(
            method=method,
            url=url,
            request_headers=request_headers,
            request_body=request_body,
            response_status=response_status,
            response_headers=response_headers,
            response_body=response_body,
            latency_ms=latency_ms,
            upstream=upstream, model_name=model_name, input_tokens=input_tokens,
            output_tokens=output_tokens, total_tokens=total_tokens, timestamp=timestamp,
            format=format,
        )

    def close(self):
        self.storage.close()

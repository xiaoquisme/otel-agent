"""SQLite → DuckDB migration manager."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def needs_migration(db_path: Path) -> bool:
    """Check if a SQLite database needs migration to DuckDB.

    Returns True if db_path has .db extension and the .duckdb equivalent
    does not already exist.
    """
    if db_path.suffix != ".db":
        return False
    duckdb_path = db_path.with_suffix(".duckdb")
    return not duckdb_path.exists()


def migrate_sqlite_to_duckdb(sqlite_path: Path, duckdb_path: Path) -> bool:
    """Migrate a SQLite database to DuckDB.

    Reads all rows from the SQLite ``requests`` table, creates a DuckDB
    database with the same schema, inserts all rows, creates indexes,
    verifies row count, and renames the original ``.db`` to ``.db.bak``.

    Returns True on success, False on failure.
    """
    try:
        import duckdb
    except ImportError:
        return False

    try:
        # Read all rows from SQLite
        sqlite_conn = sqlite3.connect(str(sqlite_path))
        sqlite_conn.row_factory = sqlite3.Row
        rows = sqlite_conn.execute("SELECT * FROM requests ORDER BY id").fetchall()
        sqlite_count = len(rows)
        sqlite_conn.close()

        if sqlite_count == 0:
            # No data to migrate — just rename
            sqlite_path.rename(sqlite_path.with_suffix(".db.bak"))
            return True

        # Create DuckDB database with same schema
        duckdb_conn = duckdb.connect(str(duckdb_path))
        duckdb_conn.execute(
            "CREATE SEQUENCE IF NOT EXISTS requests_id_seq START 1"
        )
        duckdb_conn.execute("""
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

        # Insert all rows
        for row in rows:
            duckdb_conn.execute(
                """INSERT INTO requests
                   (id, timestamp, method, url, upstream, request_headers,
                    request_body, response_status, response_headers,
                    response_body, latency_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["id"], row["timestamp"], row["method"], row["url"],
                    row["upstream"], row["request_headers"],
                    row["request_body"], row["response_status"],
                    row["response_headers"], row["response_body"],
                    row["latency_ms"],
                ),
            )

        # Create indexes
        duckdb_conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp)"
        )
        duckdb_conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_method ON requests(method)"
        )
        duckdb_conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(response_status)"
        )

        # Verify row count
        duckdb_count = duckdb_conn.execute(
            "SELECT COUNT(*) FROM requests"
        ).fetchone()[0]
        duckdb_conn.close()

        if duckdb_count != sqlite_count:
            return False

        # Rename original SQLite file
        sqlite_path.rename(sqlite_path.with_suffix(".db.bak"))
        return True

    except Exception:
        return False

"""Tests for SQLite → DuckDB migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from otel_agent.migration import migrate_sqlite_to_duckdb, needs_migration


def _create_sqlite_db(path: Path, row_count: int = 100) -> None:
    """Create a SQLite database with test data."""
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE requests (
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
    """)
    for i in range(row_count):
        conn.execute(
            "INSERT INTO requests (timestamp, method, url, response_status, latency_ms) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"2026-01-{i:02d}T00:00:00Z", "GET", f"http://example.com/{i}", 200, 10.0 + i),
        )
    conn.commit()
    conn.close()


def test_needs_migration_true(tmp_path: Path) -> None:
    """needs_migration returns True when .db exists and .duckdb doesn't."""
    db_path = tmp_path / "test.db"
    db_path.touch()
    assert needs_migration(db_path) is True


def test_needs_migration_false_duckdb_exists(tmp_path: Path) -> None:
    """needs_migration returns False when .duckdb already exists."""
    db_path = tmp_path / "test.db"
    duckdb_path = tmp_path / "test.duckdb"
    db_path.touch()
    duckdb_path.touch()
    assert needs_migration(db_path) is False


def test_needs_migration_false_not_db_extension(tmp_path: Path) -> None:
    """needs_migration returns False for non-.db files."""
    db_path = tmp_path / "test.duckdb"
    db_path.touch()
    assert needs_migration(db_path) is False


def test_migrate_sqlite_to_duckdb(tmp_path: Path) -> None:
    """Migration transfers all rows and renames .db to .db.bak."""
    sqlite_path = tmp_path / "test.db"
    duckdb_path = tmp_path / "test.duckdb"
    _create_sqlite_db(sqlite_path, row_count=100)

    result = migrate_sqlite_to_duckdb(sqlite_path, duckdb_path)

    assert result is True
    assert duckdb_path.exists()
    assert not sqlite_path.exists()
    assert (tmp_path / "test.db.bak").exists()

    # Verify row count
    import duckdb

    conn = duckdb.connect(str(duckdb_path), read_only=True)
    count = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    conn.close()
    assert count == 100


def test_migrate_preserves_data_integrity(tmp_path: Path) -> None:
    """Migration preserves all column values correctly."""
    sqlite_path = tmp_path / "test.db"
    duckdb_path = tmp_path / "test.duckdb"
    _create_sqlite_db(sqlite_path, row_count=10)

    result = migrate_sqlite_to_duckdb(sqlite_path, duckdb_path)
    assert result is True

    import duckdb

    conn = duckdb.connect(str(duckdb_path), read_only=True)
    row = conn.execute(
        "SELECT id, timestamp, method, url, response_status, latency_ms "
        "FROM requests WHERE id = 1"
    ).fetchone()
    conn.close()

    assert row[0] == 1
    assert row[1] == "2026-01-00T00:00:00Z"
    assert row[2] == "GET"
    assert row[3] == "http://example.com/0"
    assert row[4] == 200
    assert row[5] == 10.0


def test_migrate_empty_database(tmp_path: Path) -> None:
    """Migration of empty SQLite database just renames the file."""
    sqlite_path = tmp_path / "test.db"
    duckdb_path = tmp_path / "test.duckdb"
    _create_sqlite_db(sqlite_path, row_count=0)

    result = migrate_sqlite_to_duckdb(sqlite_path, duckdb_path)

    assert result is True
    assert not sqlite_path.exists()
    assert (tmp_path / "test.db.bak").exists()

# ------------------------------------------------------------------
# T006: Migration analytics-column coverage
# ------------------------------------------------------------------

def test_migrate_with_analytics_columns(tmp_path):
    """Migration from SQLite with analytics columns preserves them."""
    import sqlite3
    import duckdb

    sqlite_path = tmp_path / "with_analytics.db"
    duckdb_path = tmp_path / "with_analytics.duckdb"

    # Create SQLite with analytics columns
    conn = sqlite3.connect(str(sqlite_path))
    conn.execute("""
        CREATE TABLE requests (
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
            latency_ms REAL,
            model_name TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER
        )
    """)
    conn.execute(
        "INSERT INTO requests (timestamp, method, url, response_status, latency_ms, model_name, input_tokens, output_tokens, total_tokens) "
        "VALUES ('2026-01-01T00:00:00Z', 'GET', 'http://example.com', 200, 10.0, 'gpt-4', 100, 50, 150)"
    )
    conn.commit()
    conn.close()

    result = migrate_sqlite_to_duckdb(sqlite_path, duckdb_path)
    assert result is True

    conn = duckdb.connect(str(duckdb_path), read_only=True)
    row = conn.execute("SELECT model_name, input_tokens, output_tokens, total_tokens FROM requests").fetchone()
    conn.close()
    assert row[0] == "gpt-4"
    assert row[1] == 100
    assert row[2] == 50
    assert row[3] == 150


def test_migrate_without_analytics_columns(tmp_path):
    """Migration from legacy SQLite (no analytics columns) produces NULL analytics."""
    import duckdb

    sqlite_path = tmp_path / "legacy.db"
    duckdb_path = tmp_path / "legacy.duckdb"
    _create_sqlite_db(sqlite_path, row_count=5)

    result = migrate_sqlite_to_duckdb(sqlite_path, duckdb_path)
    assert result is True

    conn = duckdb.connect(str(duckdb_path), read_only=True)
    columns = [r[0] for r in conn.execute("DESCRIBE requests").fetchall()]
    assert "model_name" in columns
    assert "input_tokens" in columns

    row = conn.execute("SELECT model_name, input_tokens, output_tokens, total_tokens FROM requests WHERE id = 1").fetchone()
    conn.close()
    assert row[0] is None
    assert row[1] is None
    assert row[2] is None
    assert row[3] is None


def test_migrate_preserves_analytics_index(tmp_path):
    """Migrated DuckDB has timestamp index for range queries."""
    import duckdb

    sqlite_path = tmp_path / "idx.db"
    duckdb_path = tmp_path / "idx.duckdb"
    _create_sqlite_db(sqlite_path, row_count=10)

    result = migrate_sqlite_to_duckdb(sqlite_path, duckdb_path)
    assert result is True

    conn = duckdb.connect(str(duckdb_path), read_only=True)
    # DuckDB uses duckdb_indexes() or duckdb_indexes() table function
    indexes = [r[0] for r in conn.execute(
        "SELECT index_name FROM duckdb_indexes() WHERE table_name = 'requests'"
    ).fetchall()]
    conn.close()
    assert "idx_requests_timestamp" in indexes

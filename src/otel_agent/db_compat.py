"""Database compatibility layer — DuckDB with sqlite3 fallback."""

from __future__ import annotations

import warnings
from pathlib import Path


def get_connection(db_path: Path, read_only: bool = False):
    """Get a database connection, preferring DuckDB with sqlite3 fallback.

    Returns a DuckDB connection if available, otherwise a sqlite3 connection
    with a deprecation warning.
    """
    try:
        import duckdb

        return duckdb.connect(str(db_path), read_only=read_only)
    except ImportError:
        import sqlite3

        warnings.warn(
            "duckdb package not available — falling back to sqlite3. "
            "Install duckdb for better performance: pip install duckdb",
            DeprecationWarning,
            stacklevel=2,
        )
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        if not read_only:
            conn.execute("PRAGMA journal_mode=WAL")
        return conn


def rows_to_dicts(cursor, rows: list) -> list[dict]:
    """Convert database result rows to a list of dictionaries.

    Works with both DuckDB tuples and sqlite3.Row objects.
    """
    if not rows:
        return []

    # If rows are already dict-like (sqlite3.Row), just convert
    if hasattr(rows[0], "keys"):
        return [dict(r) for r in rows]

    # DuckDB returns tuples — use cursor.description for column names
    if cursor is not None and hasattr(cursor, "description") and cursor.description:
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    # Fallback: return as-is
    return [dict(r) if hasattr(r, "keys") else r for r in rows]

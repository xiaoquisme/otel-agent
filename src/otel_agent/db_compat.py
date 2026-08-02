"""Database compatibility layer — sqlite3 only.

.. note::
   This module is retained for backward compatibility.
   New code should use the storage abstraction layer
   (``otel_agent.storage``) instead of calling ``get_connection()`` directly.
"""

from __future__ import annotations

from pathlib import Path


def get_connection(db_path: Path, read_only: bool = False):
    """Get a sqlite3 database connection with WAL mode enabled."""
    import sqlite3

    uri = f"file:{db_path}"
    if read_only:
        uri += "?mode=ro"
    conn = sqlite3.connect(
        uri if read_only else str(db_path),
        uri=read_only,
        check_same_thread=False,
    )
    if not read_only:
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


def rows_to_dicts(cursor, rows: list) -> list[dict]:
    """Convert database result rows to a list of dictionaries.

    Works with sqlite3.Row objects.
    """
    if not rows:
        return []

    if hasattr(rows[0], "keys"):
        return [dict(r) for r in rows]

    if cursor is not None and hasattr(cursor, "description") and cursor.description:
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    return [dict(r) if hasattr(r, "keys") else r for r in rows]

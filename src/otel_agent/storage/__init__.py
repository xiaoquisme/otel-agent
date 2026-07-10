"""Storage abstraction layer for otel-agent.

Provides a pluggable backend interface for persisting and querying
telemetry request records.  Backends are selected via the ``storage``
field in ``config.yaml`` (default: ``"duckdb"``).

Example::

    from otel_agent.storage import create_storage

    storage = create_storage("duckdb", Path("~/.otel-agent/requests.duckdb"))
    storage.initialize()
    storage.log_request(method="POST", url="...", ...)
    results = storage.get_requests()
    storage.close()
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from otel_agent.storage.base import StorageBackend

BACKENDS: dict[str, str] = {
    "duckdb": "otel_agent.storage.duckdb.DuckDBStorage",
    "sqlite": "otel_agent.storage.sqlite.SQLiteStorage",
}


def create_storage(
    backend: str = "duckdb",
    db_path: Path | str | None = None,
    read_only: bool = False,
) -> "StorageBackend":
    """Instantiate a storage backend.

    Parameters
    ----------
    backend:
        Backend name — one of the keys in :data:`BACKENDS`
        (``"duckdb"`` or ``"sqlite"``).
    db_path:
        Path to the database file.
    read_only:
        Open the database in read-only mode (for dashboard / viewer use).

    Raises
    ------
    ValueError
        If *backend* is not a known name.
    ImportError
        If the backend module cannot be imported.
    """
    if backend not in BACKENDS:
        raise ValueError(
            f"Unknown storage backend '{backend}'. "
            f"Available: {', '.join(sorted(BACKENDS))}"
        )

    if db_path is None:
        raise ValueError("db_path is required")

    db_path = Path(db_path) if not isinstance(db_path, Path) else db_path

    # Lazy import so unused backends don't pull in heavy dependencies.
    module_path, class_name = BACKENDS[backend].rsplit(".", 1)
    import importlib

    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls(db_path, read_only=read_only)

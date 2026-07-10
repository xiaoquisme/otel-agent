# Research: Storage Abstraction Layer

**Date**: 2026-07-09
**Feature**: 017-storage-abstraction-layer

## Decision 1: Abstraction Mechanism

**Decision**: Python `abc.ABC` with `@abstractmethod`

**Rationale**: Python's built-in `abc` module is the standard way to define interfaces. `@abstractmethod` ensures backends implement all required methods at class instantiation time (fail-fast). No third-party dependency needed.

**Alternatives considered**:
- Protocol (PEP 544): Structural subtyping. Less explicit — doesn't enforce implementation at class definition time. Good for duck typing but worse for documentation and IDE support.
- Simple base class without ABC: No enforcement — backends could silently miss methods. Not safe.
- Java-style interface: Not Pythonic, no added benefit over ABC.

## Decision 2: Backend Discovery

**Decision**: Explicit mapping in `storage/__init__.py` factory function

```python
BACKENDS = {"duckdb": DuckDBStorage, "sqlite": SQLiteStorage}
```

**Rationale**: Simple dict lookup. No plugin system needed — only 2 known backends. Users who want custom backends can subclass and register.

**Alternatives considered**:
- Entry points / plugin system: Overkill for 2 backends.
- Dynamic import by name: Security risk, harder to debug.
- Config-driven module path: Too flexible, hard to validate.

## Decision 3: Interface Method Signatures

**Decision**: Match existing caller patterns exactly

| Method | Current Callers | Signature |
|--------|----------------|-----------|
| `log_request()` | logger.py:79 | `(method, url, request_headers, request_body, response_status, response_headers, response_body, latency_ms, upstream)` |
| `get_requests()` | dashboard/api.py:144 | `(search, method, status, cursor, limit) → dict` |
| `get_request()` | dashboard/api.py:193 | `(request_id) → dict | None` |
| `get_requests_since()` | dashboard/api.py:221 | `(last_id) → list[dict]` |
| `get_max_id()` | dashboard/api.py:242 | `() → int` |
| `get_all_filtered()` | dashboard/api.py:257 | `(search, method, status) → list[dict]` |
| `initialize()` | logger.py:37 | `() → None` (create tables) |
| `close()` | logger.py:97 | `() → None` |

**Rationale**: By matching existing signatures exactly, callers only need to change `self.conn.execute(...)` calls to `self.storage.method(...)` — minimal diff.

## Decision 4: Configuration Format

**Decision**: Add optional `storage` field to existing config.yaml

```yaml
storage: duckdb  # or "sqlite" — default: duckdb
```

**Rationale**: Consistent with existing config pattern. No new config file needed.

**Alternatives considered**:
- CLI flag `--storage`: Adds flag to every command. Overkill.
- Environment variable: Less discoverable than config file.
- Separate config section: Too verbose for a single field.

## Decision 5: Dashboard API Refactor Strategy

**Decision**: DashboardAPI gets a `StorageBackend` instance injected, replaces all `conn.execute()` calls with backend method calls.

**Rationale**: The dashboard API has the most complex query logic (pagination, filtering, caching). Moving the SQL into the backend keeps the API layer clean. The `CountCache` stays in the API layer (it's a caching concern, not storage).

## Decision 6: db_compat.py Fate

**Decision**: Keep `db_compat.py` — it's used by `migration.py` for the SQLite→DuckDB migration path. The storage abstraction lives alongside it.

**Rationale**: Migration code needs direct access to both DuckDB and SQLite connections. The storage interface is for ongoing operations, not one-time migration. Keeping both avoids breaking the migration code path.

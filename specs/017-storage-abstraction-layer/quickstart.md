# Quickstart: Storage Abstraction Layer

**Date**: 2026-07-09
**Feature**: 017-storage-abstraction-layer

## Prerequisites

- otel-agent installed in dev mode: `uv sync --group dev`
- Existing telemetry database with some logged requests

## Validation Scenarios

### Scenario 1: All existing tests pass (refactor verification)

```bash
PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/ -v -m "not integration"
```

**Expected**: 127/127 pass, 0 failures, no test code modified

### Scenario 2: DuckDB backend works via factory

```bash
PYTHONPATH="$(pwd):$(pwd)/src" uv run python -c "
from pathlib import Path
from otel_agent.storage import create_storage
s = create_storage('duckdb', Path('/tmp/test_storage.duckdb'))
s.initialize()
s.log_request('GET', 'http://test.com', {}, '', 200, {}, 'ok', 10.0, '')
result = s.get_requests(limit=1)
print('DuckDB backend:', result)
s.close()
"
```

**Expected**: Request stored and retrieved successfully

### Scenario 3: SQLite backend works via factory

```bash
PYTHONPATH="$(pwd):$(pwd)/src" uv run python -c "
from pathlib import Path
from otel_agent.storage import create_storage
s = create_storage('sqlite', Path('/tmp/test_storage.db'))
s.initialize()
s.log_request('GET', 'http://test.com', {}, '', 200, {}, 'ok', 10.0, '')
result = s.get_requests(limit=1)
print('SQLite backend:', result)
s.close()
"
```

**Expected**: Request stored and retrieved successfully

### Scenario 4: Invalid backend name raises error

```bash
PYTHONPATH="$(pwd):$(pwd)/src" uv run python -c "
from pathlib import Path
from otel_agent.storage import create_storage
s = create_storage('postgres', Path('/tmp/test.db'))
" 2>&1
```

**Expected**: `ValueError: Unknown storage backend 'postgres'. Valid options: duckdb, sqlite`

### Scenario 5: Config-based backend selection

1. Set `storage: sqlite` in `~/.otel-agent/config.yaml`
2. Start proxy: `uv run otel-agent proxy`
3. Send a request through the proxy
4. Check that the database file is `.db` (SQLite), not `.duckdb`
5. Restore config to `storage: duckdb`

### Scenario 6: Proxy and dashboard work with DuckDB backend

1. Start proxy: `uv run otel-agent proxy`
2. Send several requests
3. Start dashboard: `uv run otel-agent dashboard`
4. Open dashboard in browser, verify requests display correctly
5. **Expected**: All data renders, pagination works, export works

### Scenario 7: CLI view command works

```bash
uv run otel-agent view
```

**Expected**: Request list displays correctly (same output as before refactor)

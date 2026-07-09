# Quickstart: SQLite to DuckDB Migration

**Date**: 2026-07-09
**Feature**: 013-sqlite-to-duckdb-migration

## Prerequisites

- Python 3.10+
- `uv` package manager
- `duckdb` Python package (installed via `uv sync`)

## Validation Scenarios

### Scenario 1: Fresh Installation (P1)

**Setup**: No existing database.

```bash
cd /path/to/otel-agent
uv sync
uv run otel-agent proxy --port 8080
```

**Steps**:
1. Start the proxy
2. Send a request: `curl http://localhost:8080/v1/models`
3. Check for `.duckdb` file in the default data directory

**Expected outcome**:
- A `.duckdb` file is created
- The request appears in the database
- No `.db` file is created

### Scenario 2: Migration from SQLite (P1)

**Setup**: Existing SQLite database with data.

```bash
# Create a test SQLite database
python3 -c "
import sqlite3
conn = sqlite3.connect('test.db')
conn.execute('CREATE TABLE requests (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, method TEXT, url TEXT, upstream TEXT, request_headers TEXT, request_body TEXT, response_status INTEGER, response_headers TEXT, response_body TEXT, latency_ms REAL)')
for i in range(100):
    conn.execute('INSERT INTO requests (timestamp, method, url, response_status, latency_ms) VALUES (?, ?, ?, ?, ?)', (f'2026-01-{i:02d}T00:00:00Z', 'GET', f'http://example.com/{i}', 200, 10.0+i))
conn.commit()
conn.close()
"
```

**Steps**:
1. Start the proxy with the existing `.db` file
2. Wait for migration to complete

**Expected outcome**:
- `.duckdb` file is created with 100 rows
- Original `.db` file is renamed to `.db.bak`
- Row count matches (100 rows in both)

### Scenario 3: Dashboard Compatibility (P2)

**Setup**: DuckDB database with data.

```bash
uv run otel-agent dashboard --db ./data/requests.duckdb
```

**Steps**:
1. Open `http://localhost:8080` in browser
2. Verify request list loads
3. Click a request row to view details
4. Use search/filter controls
5. Click Export CSV

**Expected outcome**:
- Request list shows all columns correctly
- Detail view shows headers and body
- Search/filter returns correct results
- Export produces valid CSV

### Scenario 4: CLI Viewer Compatibility (P3)

**Setup**: DuckDB database with data.

```bash
uv run otel-agent view --db ./data/requests.duckdb
```

**Steps**:
1. Run the view command
2. Verify output format

**Expected outcome**:
- Output shows request entries in the same tabular format as before
- `--upstream` filter works correctly

### Scenario 5: Fallback to SQLite (P1)

**Setup**: DuckDB not available (simulate by renaming duckdb package).

**Steps**:
1. Start the proxy without duckdb installed
2. Send a request

**Expected outcome**:
- Deprecation warning is printed
- Proxy falls back to SQLite
- Request is logged to `.db` file
- All functionality works as before

## References

- [Storage API Contract](./contracts/storage-api.md) — interface specifications
- [Data Model](./data-model.md) — table schema and migration rules

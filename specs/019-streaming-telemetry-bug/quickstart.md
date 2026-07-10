# Quickstart: Streaming Telemetry Bug Fix Validation

**Feature**: 019-streaming-telemetry-bug

## Prerequisites

- Python 3.13+ with `uv` installed
- Project dependencies installed: `uv sync --group dev`
- No external network required (all tests use mocks)

## Validation Scenarios

### Scenario 1: Streaming Request Logged (Happy Path)

**What it proves**: A successful streaming request is recorded to telemetry.

```bash
cd /path/to/otel-agent
PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/test_server.py -v -k "test_streaming_telemetry_logged"
```

**Expected**: Test passes — telemetry record exists with `{"streamed": true, "preview": "..."}`.

### Scenario 2: Client Disconnect Mid-Stream

**What it proves**: A partially-consumed stream is still logged.

```bash
PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/test_server.py -v -k "test_streaming_client_disconnect"
```

**Expected**: Test passes — telemetry record exists even though client disconnected before stream completed.

### Scenario 3: Non-Streaming After Streaming

**What it proves**: Subsequent non-streaming requests work after streaming.

```bash
PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/test_server.py -v -k "test_nonstreaming_after_streaming"
```

**Expected**: Both requests logged. Non-streaming request has full response body.

### Scenario 4: All Existing Tests Pass

**What it proves**: Fix doesn't break existing functionality.

```bash
PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest -x -q -m "not integration"
```

**Expected**: All 127+ unit tests pass, zero failures.

## Running All Validation

```bash
PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/test_server.py -v -m "not integration"
```

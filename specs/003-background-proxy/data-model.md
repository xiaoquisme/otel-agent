# Data Model: Background Proxy Management

**Feature**: 003-background-proxy
**Date**: 2026-06-26

## Entities

### PID File (`~/.otel-agent/proxy.pid`)

| Field | Type   | Description                    |
| ----- | ------ | ------------------------------ |
| pid   | int    | Process ID of the proxy daemon |

**Format**: Single line containing the PID integer.

**Lifecycle**:
- Created when proxy starts in background
- Deleted when proxy stops (graceful or detected stale)
- Checked by `status`, `stop`, `restart`, `logs` commands

### Log File (`~/.otel-agent/proxy.log`)

| Field   | Type   | Description                        |
| ------- | ------ | ---------------------------------- |
| content | text   | Append-only stdout/stderr from proxy |

**Format**: Plain text, one line per log entry.

**Lifecycle**:
- Created when proxy starts in background (append mode)
- Read by `logs` command
- Tailed by `logs --follow`
- Not auto-rotated (user can truncate)

### Proxy Process

| Field       | Type    | Description                          |
| ----------- | ------- | ------------------------------------ |
| pid         | int     | Process ID                           |
| port        | int     | Listening port                       |
| config_path | string  | Config file used                     |
| db_path     | string  | SQLite database path                 |
| started_at  | string  | ISO timestamp (from log file)        |

**State transitions**:
```
not_running → running   (otel-agent proxy start)
running → not_running   (otel-agent proxy stop / crash / SIGTERM)
running → running       (otel-agent proxy restart = stop + start)
```

## Validation Rules

1. PID file must contain a single integer
2. PID must correspond to a running process (check with `os.kill(pid, 0)`)
3. If PID is stale (process not running), delete PID file and report "not running"
4. Log file must be writable at proxy start time
5. Port must be available before starting proxy

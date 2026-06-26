# CLI Contract: Background Proxy Management

**Feature**: 003-background-proxy

## Command Structure

```
otel-agent proxy [subcommand] [flags]
```

## Subcommands

### `otel-agent proxy start` (default)

Start the proxy in the background.

| Flag | Short | Type   | Default                      | Description                    |
| ---- | ----- | ------ | ---------------------------- | ------------------------------ |
| --port | -p  | int    | 8080                         | Proxy listen port              |
| --upstream | -u | string | ""                         | Override all upstreams         |
| --db | -d    | string | telemetry.db                 | SQLite database path           |
| --config | -c  | string | ~/.otel-agent/config.yaml    | Config file path               |
| --foreground | -f | bool | false                     | Run in foreground (blocking)   |

**Exit codes**:
- 0: Proxy started successfully
- 1: Proxy already running, or port in use, or config error

**Output**:
```
Proxy started on :8080 (PID 12345)
Logging to ~/.otel-agent/proxy.log
```

---

### `otel-agent proxy stop`

Stop the running proxy.

**Exit codes**:
- 0: Proxy stopped successfully
- 0: No proxy running (prints message, exits 0)

**Output**:
```
Proxy stopped.
```
or
```
No proxy is running.
```

---

### `otel-agent proxy restart`

Stop and start the proxy. Accepts same flags as `start`.

**Exit codes**:
- 0: Proxy restarted successfully
- 0: No proxy was running (starts fresh)

**Output**:
```
Proxy stopped.
Proxy started on :8080 (PID 12346)
```

---

### `otel-agent proxy status`

Check if the proxy is running.

**Exit codes**:
- 0: Proxy is running
- 0: Proxy is not running

**Output**:
```
Proxy running on :8080 (PID 12345)
```
or
```
Proxy is not running.
```

---

### `otel-agent proxy logs`

Show recent proxy log output.

| Flag | Short | Type | Default | Description |
| ---- | ----- | ---- | ------- | ----------- |
| --follow | -F | bool | false | Stream new lines in real-time |
| --lines | -n | int | 50 | Number of recent lines to show |

**Exit codes**:
- 0: Logs displayed
- 0: No proxy running (for --follow only)

**Output**: Last N lines of `~/.otel-agent/proxy.log`

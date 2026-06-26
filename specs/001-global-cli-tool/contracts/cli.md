# CLI Contract: otel-agent

**Feature**: 001-global-cli-tool

## Command Structure

```
otel-agent [--version] [--help] <command> [<args>]
```

## Commands

### `otel-agent init`

Create default config file at `~/.otel-agent/config.yaml`.

| Flag | Short | Type   | Default                      | Description           |
| ---- | ----- | ------ | ---------------------------- | --------------------- |
| --config | -c  | string | `~/.otel-agent/config.yaml` | Config file path      |

**Exit codes**:
- 0: Config created successfully
- 0: Config already exists (warning printed, no overwrite)
- 1: Parent directory creation failed

**Output**:
```
Created config: ~/.otel-agent/config.yaml
Edit it to add your API keys.
```

---

### `otel-agent proxy`

Start the MITM proxy.

| Flag | Short | Type   | Default                      | Description           |
| ---- | ----- | ------ | ---------------------------- | --------------------- |
| --port | -p  | int    | 8080                         | Proxy listen port     |
| --upstream | -u | string | ""                         | Override all upstreams |
| --db | -d    | string | `telemetry.db`               | SQLite database path  |
| --config | -c  | string | `~/.otel-agent/config.yaml` | Config file path      |

**Exit codes**:
- 0: Graceful shutdown (Ctrl+C)
- 1: Port already in use
- 1: Config file invalid YAML

**Output (startup)**:
```
otel-proxy listening on :8080
logging to telemetry.db
config: ~/.otel-agent/config.yaml
  provider: openai (2/3 keys active)
  provider: anthropic (1/2 keys active)
Ctrl+C to stop
```

---

### `otel-agent view`

Display logged requests.

| Flag | Short | Type   | Default | Description                    |
| ---- | ----- | ------ | ------- | ------------------------------ |
| --filter | -f | string | ""     | Filter by upstream substring   |
| --limit | -n  | int    | 20     | Max rows to display            |
| --db | -d    | string | `telemetry.db` | SQLite database path |

**Exit codes**:
- 0: Requests displayed or "No requests logged yet."

**Output**:
```
[1] 2026-06-26T10:00:00 | POST https://api.openai.com/v1/chat/completions
  upstream: https://api.openai.com/v1/chat/completions
  status: 200 | latency: 1234ms
  request: {"model":"gpt-4","messages":[...]}
```

---

### `otel-agent config path`

Print the config file path.

**Output**: `~/.otel-agent/config.yaml`

---

### `otel-agent config show`

Display config with API keys masked.

**Output**:
```yaml
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-proj-***
        active: true
```

---

### `otel-agent config edit`

Open config in `$EDITOR`. Falls back to `vim` if `$EDITOR` is not set.

---

### `otel-agent doctor`

Check installation health.

**Checks**:
- Python version >= 3.10
- mitmproxy importable
- Config file exists and is valid YAML
- Port 8080 available (optional warning)

**Output**:
```
otel-agent doctor

  Python 3.11.15      ✅
  mitmproxy 11.0.2    ✅
  Config valid         ✅
  Port 8080            ✅ available
```

---

### `otel-agent --version`

**Output**: `otel-agent 0.1.0`

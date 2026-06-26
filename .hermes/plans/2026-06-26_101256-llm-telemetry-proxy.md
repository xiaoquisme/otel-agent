# LLM Telemetry Proxy — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a Python HTTP/HTTPS proxy that intercepts LLM API calls (OpenAI, Anthropic), logs full request/response to SQLite, and supports switching upstream targets via CLI args.

**Architecture:** A MITM HTTP proxy using `mitmproxy` as the core engine with a custom addon. The addon intercepts requests, logs them to SQLite, and optionally rewrites the upstream target. CLI args configure the proxy port, upstream target override, and log output path.

**Tech Stack:** Python 3.9+, mitmproxy, SQLite (stdlib), argparse, uv for project management.

---

## Task 1: Project scaffolding with uv

**Objective:** Initialize the project with uv and install dependencies.

**Files:**
- Create: `pyproject.toml`
- Create: `src/otel_agent/__init__.py`
- Create: `src/otel_agent/proxy.py` (main entry)

**Step 1: Create pyproject.toml**

```toml
[project]
name = "otel-agent"
version = "0.1.0"
description = "LLM API telemetry proxy"
requires-python = ">=3.9"
dependencies = [
    "mitmproxy>=10.0",
]

[project.scripts]
otel-proxy = "otel_agent.proxy:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/otel_agent"]
```

**Step 2: Create package structure**

```bash
mkdir -p src/otel_agent tests
touch src/otel_agent/__init__.py
```

**Step 3: Sync dependencies**

```bash
cd /Users/julieyang/personal/otel-agent
uv sync
```

**Step 4: Commit**

```bash
git init
git add -A
git commit -m "feat: project scaffolding with uv"
```

---

## Task 2: SQLite logger module

**Objective:** Create a module that logs request/response pairs to SQLite.

**Files:**
- Create: `src/otel_agent/logger.py`
- Create: `tests/test_logger.py`

**Step 1: Write failing test**

```python
# tests/test_logger.py
import json
import sqlite3
import tempfile
from pathlib import Path
from otel_agent.logger import TelemetryLogger


def test_creates_db_and_tables():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        logger.close()
        conn = sqlite3.connect(str(db_path))
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        assert "requests" in tables


def test_log_request_inserts_row():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        logger.log_request(
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            request_headers={"Authorization": "Bearer sk-test", "Content-Type": "application/json"},
            request_body='{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}',
            response_status=200,
            response_headers={"content-type": "application/json"},
            response_body='{"choices":[{"message":{"content":"hello"}}]}',
            latency_ms=1234.5,
            upstream="https://api.openai.com",
        )
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT method, url, upstream, latency_ms FROM requests").fetchone()
        conn.close()
        assert row[0] == "POST"
        assert "openai.com" in row[1]
        assert row[2] == "https://api.openai.com"
        assert row[3] == 1234.5


def test_log_preserves_full_payload():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        body = json.dumps({"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]})
        logger.log_request(
            method="POST", url="https://api.openai.com/v1/chat/completions",
            request_headers={}, request_body=body,
            response_status=200, response_headers={},
            response_body='{"choices":[]}', latency_ms=100.0,
            upstream="https://api.openai.com",
        )
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT request_body FROM requests").fetchone()
        conn.close()
        parsed = json.loads(row[0])
        assert parsed["model"] == "gpt-4"
```

**Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_logger.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'otel_agent.logger'`

**Step 3: Write minimal implementation**

```python
# src/otel_agent/logger.py
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class TelemetryLogger:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                method TEXT NOT NULL,
                url TEXT NOT NULL,
                upstream TEXT,
                request_headers TEXT,
                request_body TEXT,
                response_status INTEGER,
                response_headers TEXT,
                response_body TEXT,
                latency_ms REAL
            )
        """)
        self.conn.commit()

    def log_request(
        self,
        method: str,
        url: str,
        request_headers: dict,
        request_body: str,
        response_status: int,
        response_headers: dict,
        response_body: str,
        latency_ms: float,
        upstream: str = "",
    ):
        self.conn.execute(
            """INSERT INTO requests
               (timestamp, method, url, upstream, request_headers, request_body,
                response_status, response_headers, response_body, latency_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                method, url, upstream,
                json.dumps(request_headers),
                request_body,
                response_status,
                json.dumps(response_headers),
                response_body,
                latency_ms,
            ),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
```

**Step 4: Run test to verify pass**

```bash
uv run pytest tests/test_logger.py -v
```

Expected: 3 passed

**Step 5: Commit**

```bash
git add src/otel_agent/logger.py tests/test_logger.py
git commit -m "feat: SQLite telemetry logger"
```

---

## Task 3: mitmproxy addon — intercept and log

**Objective:** Create the mitmproxy addon that intercepts every HTTP request/response and logs it via TelemetryLogger.

**Files:**
- Create: `src/otel_agent/addon.py`
- Create: `tests/test_addon.py`

**Step 1: Write failing test**

```python
# tests/test_addon.py
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from otel_agent.addon import TelemetryAddon
from otel_agent.logger import TelemetryLogger


def _make_flow(method="POST", url="https://api.openai.com/v1/chat/completions",
               req_body='{"model":"gpt-4"}', resp_body='{"choices":[]}',
               resp_status=200):
    """Create a mock mitmproxy flow."""
    flow = MagicMock()
    flow.request.method = method
    flow.request.url = url
    flow.request.headers = {"Authorization": "Bearer sk-test"}
    flow.request.get_content.return_value = req_body.encode()
    flow.response = MagicMock()
    flow.response.status_code = resp_status
    flow.response.headers = {"content-type": "application/json"}
    flow.response.get_content.return_value = resp_body.encode()
    flow.response.timestamp_start = 1000.0
    flow.response.timestamp_end = 1001.5
    return flow


def test_addon_logs_request():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        addon = TelemetryAddon(logger, upstream_override="")

        flow = _make_flow()
        addon.response(flow)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT method, request_body FROM requests").fetchone()
        conn.close()
        assert row[0] == "POST"
        assert "gpt-4" in row[1]
        logger.close()


def test_addon_calculates_latency():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        logger = TelemetryLogger(db_path)
        addon = TelemetryAddon(logger, upstream_override="")

        flow = _make_flow()
        flow.response.timestamp_start = 1000.0
        flow.response.timestamp_end = 1001.5
        addon.response(flow)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT latency_ms FROM requests").fetchone()
        conn.close()
        assert row[0] == 1500.0  # (1001.5 - 1000.0) * 1000
        logger.close()
```

**Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_addon.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'otel_agent.addon'`

**Step 3: Write minimal implementation**

```python
# src/otel_agent/addon.py
from mitmproxy import http
from otel_agent.logger import TelemetryLogger


class TelemetryAddon:
    def __init__(self, logger: TelemetryLogger, upstream_override: str = ""):
        self.logger = logger
        self.upstream_override = upstream_override

    def request(self, flow: http.HTTPFlow):
        """Optionally rewrite the upstream target."""
        if self.upstream_override:
            from urllib.parse import urlparse
            parsed = urlparse(self.upstream_override)
            flow.request.scheme = parsed.scheme
            flow.request.host = parsed.hostname
            if parsed.port:
                flow.request.port = parsed.port
            elif parsed.scheme == "https":
                flow.request.port = 443
            else:
                flow.request.port = 80

    def response(self, flow: http.HTTPFlow):
        """Log every completed request/response."""
        req_body = flow.request.get_content().decode("utf-8", errors="replace")
        resp_body = flow.response.get_content().decode("utf-8", errors="replace") if flow.response else ""

        latency = 0.0
        if flow.response and flow.response.timestamp_start and flow.response.timestamp_end:
            latency = (flow.response.timestamp_end - flow.response.timestamp_start) * 1000

        self.logger.log_request(
            method=flow.request.method,
            url=flow.request.url,
            request_headers=dict(flow.request.headers),
            request_body=req_body,
            response_status=flow.response.status_code if flow.response else 0,
            response_headers=dict(flow.response.headers) if flow.response else {},
            response_body=resp_body,
            latency_ms=latency,
            upstream=self.upstream_override or flow.request.url,
        )
```

**Step 4: Run test to verify pass**

```bash
uv run pytest tests/test_addon.py -v
```

Expected: 2 passed

**Step 5: Commit**

```bash
git add src/otel_agent/addon.py tests/test_addon.py
git commit -m "feat: mitmproxy addon for intercepting and logging LLM requests"
```

---

## Task 4: CLI entry point

**Objective:** Create the main CLI entry point that wires up the proxy with argparse.

**Files:**
- Create: `src/otel_agent/proxy.py`
- Create: `tests/test_proxy.py`

**Step 1: Write failing test**

```python
# tests/test_proxy.py
import argparse
from otel_agent.proxy import build_parser


def test_parser_defaults():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.port == 8080
    assert args.upstream == ""
    assert args.db == "telemetry.db"


def test_parser_custom_values():
    parser = build_parser()
    args = parser.parse_args([
        "--port", "9090",
        "--upstream", "https://api.anthropic.com",
        "--db", "/tmp/logs.db",
    ])
    assert args.port == 9090
    assert args.upstream == "https://api.anthropic.com"
    assert args.db == "/tmp/logs.db"


def test_parser_short_flags():
    parser = build_parser()
    args = parser.parse_args(["-p", "3128", "-u", "https://localhost:8888"])
    assert args.port == 3128
    assert args.upstream == "https://localhost:8888"
```

**Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_proxy.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# src/otel_agent/proxy.py
import argparse
import sys
from pathlib import Path

from mitmproxy.options import Options
from mitmproxy.tools.dump import DumpMaster

from otel_agent.addon import TelemetryAddon
from otel_agent.logger import TelemetryLogger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="otel-proxy",
        description="LLM API telemetry proxy — intercept, log, redirect.",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=8080,
        help="Proxy listen port (default: 8080)",
    )
    parser.add_argument(
        "-u", "--upstream", type=str, default="",
        help="Override upstream target, e.g. https://api.anthropic.com",
    )
    parser.add_argument(
        "-d", "--db", type=str, default="telemetry.db",
        help="SQLite database path (default: telemetry.db)",
    )
    return parser


async def run_proxy(args):
    logger = TelemetryLogger(Path(args.db))
    addon = TelemetryAddon(logger, upstream_override=args.upstream)

    opts = Options(listen_port=args.port)
    master = DumpMaster(opts)
    master.addons.add(addon)

    upstream_msg = f" -> {args.upstream}" if args.upstream else ""
    print(f"otel-proxy listening on :{args.port}{upstream_msg}")
    print(f"logging to {args.db}")
    print("Ctrl+C to stop\n")

    try:
        await master.run()
    except KeyboardInterrupt:
        pass
    finally:
        master.shutdown()
        logger.close()


def main():
    parser = build_parser()
    args = parser.parse_args()

    import asyncio
    asyncio.run(run_proxy(args))


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify pass**

```bash
uv run pytest tests/test_proxy.py -v
```

Expected: 3 passed

**Step 5: Commit**

```bash
git add src/otel_agent/proxy.py tests/test_proxy.py
git commit -m "feat: CLI entry point with argparse"
```

---

## Task 5: CLI viewer — query logged requests

**Objective:** Add a subcommand to view/query logged requests from the SQLite DB.

**Files:**
- Create: `src/otel_agent/viewer.py`
- Create: `tests/test_viewer.py`

**Step 1: Write failing test**

```python
# tests/test_viewer.py
import tempfile
from pathlib import Path
from otel_agent.logger import TelemetryLogger
from otel_agent.viewer import query_requests, format_request


def test_query_returns_all():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        logger = TelemetryLogger(db)
        logger.log_request("POST", "https://api.openai.com/v1/chat/completions",
                           {}, '{"model":"gpt-4"}', 200, {}, '{"choices":[]}',
                           100.0, "https://api.openai.com")
        logger.log_request("POST", "https://api.anthropic.com/v1/messages",
                           {}, '{"model":"claude-3"}', 200, {}, '{"content":[]}',
                           200.0, "https://api.anthropic.com")
        logger.close()

        rows = query_requests(db)
        assert len(rows) == 2


def test_query_filters_by_upstream():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        logger = TelemetryLogger(db)
        logger.log_request("POST", "https://api.openai.com/v1/chat/completions",
                           {}, '{}', 200, {}, '{}', 100.0, "https://api.openai.com")
        logger.log_request("POST", "https://api.anthropic.com/v1/messages",
                           {}, '{}', 200, {}, '{}', 200.0, "https://api.anthropic.com")
        logger.close()

        rows = query_requests(db, upstream_filter="openai")
        assert len(rows) == 1


def test_format_request():
    row = {
        "id": 1, "timestamp": "2026-06-26T10:00:00",
        "method": "POST", "url": "https://api.openai.com/v1/chat/completions",
        "upstream": "https://api.openai.com",
        "request_body": '{"model":"gpt-4"}',
        "response_status": 200, "latency_ms": 123.4,
    }
    text = format_request(row)
    assert "POST" in text
    assert "200" in text
    assert "gpt-4" in text
```

**Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_viewer.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# src/otel_agent/viewer.py
import sqlite3
from pathlib import Path


def query_requests(db_path: Path, upstream_filter: str = "", limit: int = 50) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if upstream_filter:
        rows = conn.execute(
            "SELECT * FROM requests WHERE upstream LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{upstream_filter}%", limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM requests ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def format_request(row: dict) -> str:
    return (
        f"[{row['id']}] {row['timestamp']} | {row['method']} {row['url']}\n"
        f"  upstream: {row.get('upstream', 'N/A')}\n"
        f"  status: {row.get('response_status', '?')} | latency: {row.get('latency_ms', 0):.0f}ms\n"
        f"  request: {row.get('request_body', '')[:200]}\n"
    )
```

**Step 4: Run test to verify pass**

```bash
uv run pytest tests/test_viewer.py -v
```

Expected: 3 passed

**Step 5: Commit**

```bash
git add src/otel_agent/viewer.py tests/test_viewer.py
git commit -m "feat: CLI viewer for querying logged requests"
```

---

## Task 6: Wire viewer into CLI as subcommand

**Objective:** Add `otel-proxy view` subcommand to the CLI.

**Files:**
- Modify: `src/otel_agent/proxy.py`

**Step 1: Update proxy.py with subcommand**

Add to `build_parser`:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="otel-proxy",
        description="LLM API telemetry proxy — intercept, log, redirect.",
    )
    sub = parser.add_subparsers(dest="command")

    # proxy command (default)
    proxy_p = sub.add_parser("proxy", help="Run the proxy")
    proxy_p.add_argument("-p", "--port", type=int, default=8080)
    proxy_p.add_argument("-u", "--upstream", type=str, default="")
    proxy_p.add_argument("-d", "--db", type=str, default="telemetry.db")

    # view command
    view_p = sub.add_parser("view", help="View logged requests")
    view_p.add_argument("-d", "--db", type=str, default="telemetry.db")
    view_p.add_argument("-f", "--filter", type=str, default="",
                        help="Filter by upstream (substring match)")
    view_p.add_argument("-n", "--limit", type=int, default=20)

    return parser
```

Update `main()` to dispatch:

```python
def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "view":
        from otel_agent.viewer import query_requests, format_request
        from pathlib import Path
        rows = query_requests(Path(args.db), args.filter, args.limit)
        if not rows:
            print("No requests logged yet.")
        for r in rows:
            print(format_request(r))
    else:
        import asyncio
        asyncio.run(run_proxy(args))
```

**Step 2: Test manually**

```bash
uv run otel-proxy view -d telemetry.db
```

Expected: "No requests logged yet." (empty db)

**Step 3: Commit**

```bash
git add src/otel_agent/proxy.py
git commit -m "feat: view subcommand for querying logged requests"
```

---

## Task 7: Integration test — proxy end-to-end

**Objective:** Verify the proxy starts, intercepts a request, and logs it.

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

```python
# tests/test_integration.py
import json
import sqlite3
import tempfile
import subprocess
import time
from pathlib import Path
import pytest
import requests


@pytest.mark.integration
def test_proxy_logs_request():
    """Start proxy, send a request through it, check it was logged."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        # Start proxy on a random high port
        proc = subprocess.Popen(
            ["uv", "run", "otel-proxy", "proxy", "-p", "18765", "-d", str(db_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        time.sleep(2)  # wait for startup

        try:
            # Send a request through the proxy to httpbin (not an LLM API, just for testing)
            resp = requests.get(
                "https://httpbin.org/get",
                proxies={"https": "http://127.0.0.1:18765", "http": "http://127.0.0.1:18765"},
                timeout=10,
                verify=False,  # mitmproxy uses self-signed cert
            )
            assert resp.status_code == 200

            time.sleep(1)  # wait for logging

            conn = sqlite3.connect(str(db_path))
            rows = conn.execute("SELECT * FROM requests").fetchall()
            conn.close()
            assert len(rows) >= 1
        finally:
            proc.terminate()
            proc.wait()
```

**Step 2: Run integration test**

```bash
uv run pytest tests/test_integration.py -v -m integration
```

Expected: 1 passed (or skipped if network unavailable)

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "feat: integration test for proxy e2e"
```

---

## Task 8: README and usage documentation

**Objective:** Write a clear README with usage examples.

**Files:**
- Create: `README.md`

**Step 1: Write README**

```markdown
# otel-agent — LLM Telemetry Proxy

Intercept, log, and redirect LLM API calls (OpenAI, Anthropic, etc.).

## Install

```bash
uv sync
```

## Usage

### Start proxy (default port 8080)

```bash
uv run otel-proxy proxy
```

### Redirect all traffic to a different upstream

```bash
uv run otel-proxy proxy --upstream https://api.anthropic.com
```

### Custom port and DB path

```bash
uv run otel-proxy proxy -p 9090 -d /tmp/llm-logs.db
```

### View logged requests

```bash
uv run otel-proxy view
uv run otel-proxy view --filter openai --limit 50
```

### Use with Python requests

```python
import requests

resp = requests.post(
    "https://api.openai.com/v1/chat/completions",
    json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
    headers={"Authorization": "Bearer sk-..."},
    proxies={"https": "http://127.0.0.1:8080"},
    verify=False,  # mitmproxy self-signed cert
)
```

### Use with OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    http_client=httpx.Client(
        proxies="http://127.0.0.1:8080",
        verify=False,
    )
)
```

## Schema

Each logged request includes:
- `timestamp`, `method`, `url`, `upstream`
- `request_headers`, `request_body` (full JSON)
- `response_status`, `response_headers`, `response_body`
- `latency_ms`
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with usage examples"
```

---

## Files that will exist after implementation

```
otel-agent/
├── pyproject.toml
├── README.md
├── src/otel_agent/
│   ├── __init__.py
│   ├── proxy.py          # CLI entry point
│   ├── addon.py           # mitmproxy addon (intercept + log)
│   ├── logger.py          # SQLite logger
│   └── viewer.py          # Query/display logged requests
└── tests/
    ├── test_logger.py
    ├── test_addon.py
    ├── test_proxy.py
    ├── test_viewer.py
    └── test_integration.py
```

## Risks & Tradeoffs

- **mitmproxy cert**: Clients need `verify=False` or the mitmproxy CA cert installed. Document this clearly.
- **Streaming responses**: mitmproxy buffers responses by default. For streaming LLM responses, may need `stream_large_bodies` option — defer to v2.
- **Performance**: SQLite WAL mode handles concurrent writes, but heavy load may need batched inserts — defer unless needed.
- **Sensitive data**: Auth headers and API keys are logged in full. Consider redaction as a follow-up.

## Open Questions

- Should we support WebSocket logging (for streaming SSE from LLM APIs)?
- Should we redact Authorization headers in logs?
- Do we need a `--redact` flag?

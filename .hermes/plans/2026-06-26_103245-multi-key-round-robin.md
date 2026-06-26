# Config-Driven Multi-Key Rotation for LLM Telemetry Proxy

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Move all provider/key config to `~/.otel-agent/config.yaml`, support multiple active keys per provider with round-robin rotation, and hot-reload config on each request.

**Architecture:** Add a `Config` class that loads and watches `~/.otel-agent/config.yaml`. Each provider defines its `base_url` and a list of keys with `active: true/false`. The addon reads the config on every request, filters to active keys, and round-robins. The `--upstream` and `-k` CLI args become optional overrides for quick one-off use.

**Tech Stack:** Python 3.10+, PyYAML (via mitmproxy dep), mitmproxy, watchdog (optional, for file watching)

---

## Config File Format

```yaml
# ~/.otel-agent/config.yaml
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-proj-key1
        active: true
      - key: sk-proj-key2
        active: true
      - key: sk-proj-key3
        active: false   # disabled, won't be used until toggled

  anthropic:
    base_url: https://api.anthropic.com
    keys:
      - key: sk-ant-key1
        active: true
      - key: sk-ant-key2
        active: false

  deepseek:
    base_url: https://api.deepseek.com/v1
    keys:
      - key: sk-ds-key1
        active: true
```

---

### Task 1: Add PyYAML dependency and create Config loader

**Objective:** Create a `Config` class that loads `~/.otel-agent/config.yaml`, validates it, and provides provider/key lookups.

**Files:**
- Create: `src/otel_agent/config.py`
- Create: `tests/test_config.py`
- Modify: `pyproject.toml` (add pyyaml dep)

**Step 1: Add pyyaml to dependencies**

```bash
uv add pyyaml
```

**Step 2: Write failing tests**

```python
# tests/test_config.py
import tempfile
from pathlib import Path
from otel_agent.config import Config


def test_load_valid_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
      - key: sk-b
        active: false
""")
    cfg = Config(config_file)
    provider = cfg.get_provider("openai.com")
    assert provider is not None
    assert provider.base_url == "https://api.openai.com/v1"


def test_active_keys_only(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
      - key: sk-b
        active: false
      - key: sk-c
        active: true
""")
    cfg = Config(config_file)
    keys = cfg.get_active_keys("openai.com")
    assert keys == ["sk-a", "sk-c"]


def test_host_matching(tmp_path):
    """Match by substring: 'openai' matches 'api.openai.com'."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
""")
    cfg = Config(config_file)
    assert cfg.get_provider("api.openai.com") is not None
    assert cfg.get_provider("api.anthropic.com") is None


def test_all_keys_inactive(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: false
""")
    cfg = Config(config_file)
    keys = cfg.get_active_keys("openai.com")
    assert keys == []


def test_missing_config_returns_empty():
    cfg = Config(Path("/nonexistent/config.yaml"))
    assert cfg.get_provider("openai.com") is None
    assert cfg.get_active_keys("openai.com") == []


def test_reload_on_change(tmp_path):
    """Config re-reads on each call, so file changes take effect."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
""")
    cfg = Config(config_file)
    assert cfg.get_active_keys("openai.com") == ["sk-a"]

    # Toggle key off and add new one
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: false
      - key: sk-b
        active: true
""")
    assert cfg.get_active_keys("openai.com") == ["sk-b"]
```

**Step 3: Run tests to verify failure**

```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 4: Implement Config class**

```python
# src/otel_agent/config.py
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class KeyEntry:
    key: str
    active: bool = True


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    keys: list[KeyEntry] = field(default_factory=list)

    def active_keys(self) -> list[str]:
        return [k.key for k in self.keys if k.active]


class Config:
    """Loads and hot-reloads ~/.otel-agent/config.yaml."""

    def __init__(self, path: Path):
        self.path = path
        self._mtime: float = 0
        self._providers: dict[str, ProviderConfig] = {}
        self._reload()

    def _reload(self):
        if not self.path.exists():
            self._providers = {}
            return

        stat = self.path.stat().st_mtime
        if stat == self._mtime:
            return
        self._mtime = stat

        with open(self.path) as f:
            data = yaml.safe_load(f) or {}

        providers = {}
        for name, pconf in (data.get("providers") or {}).items():
            keys = []
            for entry in (pconf.get("keys") or []):
                if isinstance(entry, dict):
                    keys.append(KeyEntry(
                        key=entry.get("key", ""),
                        active=bool(entry.get("active", True)),
                    ))
                elif isinstance(entry, str):
                    keys.append(KeyEntry(key=entry, active=True))
            providers[name] = ProviderConfig(
                name=name,
                base_url=pconf.get("base_url", ""),
                keys=keys,
            )
        self._providers = providers

    def get_provider(self, host: str) -> Optional[ProviderConfig]:
        """Find a provider whose name is a substring of host."""
        self._reload()
        for name, provider in self._providers.items():
            if name in host:
                return provider
        return None

    def get_active_keys(self, host: str) -> list[str]:
        self._reload()
        provider = self.get_provider(host)
        if provider:
            return provider.active_keys()
        return []
```

**Step 5: Run tests to verify pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 6 passed

**Step 6: Commit**

```bash
git add src/otel_agent/config.py tests/test_config.py pyproject.toml uv.lock
git commit -m "feat: config loader with hot-reload for ~/.otel-agent/config.yaml"
```

---

### Task 2: Add KeyRotator for round-robin among active keys

**Objective:** A stateful rotator that cycles through a list of keys, re-checking config each time.

**Files:**
- Create: `src/otel_agent/rotator.py`
- Create: `tests/test_rotator.py`

**Step 1: Write failing tests**

```python
# tests/test_rotator.py
import tempfile
from pathlib import Path
from otel_agent.config import Config
from otel_agent.rotator import KeyRotator


def test_rotator_cycles_keys(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
      - key: sk-b
        active: true
      - key: sk-c
        active: true
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)

    seen = [rotator.next("api.openai.com") for _ in range(6)]
    assert seen == ["sk-a", "sk-b", "sk-c", "sk-a", "sk-b", "sk-c"]


def test_rotator_skips_inactive(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
      - key: sk-b
        active: false
      - key: sk-c
        active: true
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)

    seen = [rotator.next("api.openai.com") for _ in range(4)]
    assert seen == ["sk-a", "sk-c", "sk-a", "sk-c"]


def test_rotator_picks_up_config_changes(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)

    assert rotator.next("api.openai.com") == "sk-a"

    # Change config: deactivate sk-a, activate sk-b
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: false
      - key: sk-b
        active: true
""")
    assert rotator.next("api.openai.com") == "sk-b"


def test_rotator_no_keys_returns_none(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys: []
""")
    cfg = Config(config_file)
    rotator = KeyRotator(cfg)
    assert rotator.next("api.openai.com") is None
```

**Step 2: Run tests to verify failure**

```bash
uv run pytest tests/test_rotator.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement KeyRotator**

```python
# src/otel_agent/rotator.py
from __future__ import annotations

from otel_agent.config import Config


class KeyRotator:
    """Round-robin key rotation, re-reads active keys from config each call."""

    def __init__(self, config: Config):
        self.config = config
        self._indices: dict[str, int] = {}  # host_pattern -> current index

    def next(self, host: str) -> str | None:
        """Return the next active key for the provider matching host."""
        provider = self.config.get_provider(host)
        if not provider:
            return None

        active = provider.active_keys()
        if not active:
            return None

        name = provider.name
        idx = self._indices.get(name, 0) % len(active)
        key = active[idx]
        self._indices[name] = idx + 1
        return key
```

**Step 4: Run tests to verify pass**

```bash
uv run pytest tests/test_rotator.py -v
```

Expected: 4 passed

**Step 5: Commit**

```bash
git add src/otel_agent/rotator.py tests/test_rotator.py
git commit -m "feat: round-robin key rotator with hot-reload support"
```

---

### Task 3: Rewrite addon to use Config + KeyRotator

**Objective:** Replace hardcoded `api_keys` dict with Config/KeyRotator, auto-detect provider from request host.

**Files:**
- Modify: `src/otel_agent/addon.py`
- Modify: `tests/test_addon.py`

**Step 1: Rewrite addon**

```python
# src/otel_agent/addon.py
from urllib.parse import urlparse
from mitmproxy import http
from otel_agent.config import Config
from otel_agent.logger import TelemetryLogger
from otel_agent.rotator import KeyRotator

# Provider auth header mapping
PROVIDER_AUTH = {
    "anthropic.com": "x-api-key",
}
DEFAULT_AUTH_HEADER = "Authorization"
DEFAULT_AUTH_PREFIX = "Bearer "


class TelemetryAddon:
    def __init__(
        self,
        logger: TelemetryLogger,
        config: Config,
        rotator: KeyRotator,
        upstream_override: str = "",
    ):
        self.logger = logger
        self.config = config
        self.rotator = rotator
        self.upstream_override = upstream_override

    def _inject_auth(self, flow: http.HTTPFlow, key: str):
        """Inject the appropriate auth header based on the target host."""
        host = flow.request.host
        header = DEFAULT_AUTH_HEADER
        for provider, hdr in PROVIDER_AUTH.items():
            if provider in host:
                header = hdr
                break

        if header == DEFAULT_AUTH_HEADER:
            flow.request.headers[header] = DEFAULT_AUTH_PREFIX + key
        else:
            flow.request.headers[header] = key

    def request(self, flow: http.HTTPFlow):
        """Rewrite upstream target and inject API key."""
        # Upstream override from CLI arg
        if self.upstream_override:
            parsed = urlparse(self.upstream_override)
            flow.request.scheme = parsed.scheme
            flow.request.host = parsed.hostname
            if parsed.port:
                flow.request.port = parsed.port
            elif parsed.scheme == "https":
                flow.request.port = 443
            else:
                flow.request.port = 80

        # Check if config has a provider with base_url for this host
        provider = self.config.get_provider(flow.request.host)
        if provider and provider.base_url:
            parsed = urlparse(provider.base_url)
            flow.request.scheme = parsed.scheme
            flow.request.host = parsed.hostname
            if parsed.port:
                flow.request.port = parsed.port
            elif parsed.scheme == "https":
                flow.request.port = 443
            else:
                flow.request.port = 80

        # Inject API key via rotator
        key = self.rotator.next(flow.request.host)
        if key:
            self._inject_auth(flow, key)

    def response(self, flow: http.HTTPFlow):
        """Log every completed request/response."""
        req_body = flow.request.get_content().decode("utf-8", errors="replace")
        resp_body = (
            flow.response.get_content().decode("utf-8", errors="replace")
            if flow.response
            else ""
        )

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

**Step 2: Rewrite addon tests**

```python
# tests/test_addon.py
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from otel_agent.addon import TelemetryAddon
from otel_agent.config import Config
from otel_agent.logger import TelemetryLogger
from otel_agent.rotator import KeyRotator


def _make_config(tmp_path, yaml_content):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml_content)
    return Config(config_file)


def _make_flow(method="POST", url="https://api.openai.com/v1/chat/completions",
               req_body='{"model":"gpt-4"}', resp_body='{"choices":[]}',
               resp_status=200):
    flow = MagicMock()
    flow.request.method = method
    flow.request.url = url
    flow.request.host = "api.openai.com"
    flow.request.headers = {}
    flow.request.get_content.return_value = req_body.encode()
    flow.request.scheme = "https"
    flow.request.port = 443
    flow.response = MagicMock()
    flow.response.status_code = resp_status
    flow.response.headers = {"content-type": "application/json"}
    flow.response.get_content.return_value = resp_body.encode()
    flow.response.timestamp_start = 1000.0
    flow.response.timestamp_end = 1001.5
    return flow


def _make_addon(tmp_path, yaml_content, upstream_override=""):
    db_path = tmp_path / "test.db"
    logger = TelemetryLogger(db_path)
    config = _make_config(tmp_path, yaml_content)
    rotator = KeyRotator(config)
    return TelemetryAddon(logger, config, rotator, upstream_override=upstream_override)


def test_addon_injects_openai_key(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-test123
        active: true
""")
    flow = _make_flow()
    flow.request.host = "api.openai.com"
    addon.request(flow)
    assert flow.request.headers["Authorization"] == "Bearer sk-test123"


def test_addon_injects_anthropic_key(tmp_path):
    db_path = tmp_path / "test.db"
    logger = TelemetryLogger(db_path)
    config = _make_config(tmp_path, """
providers:
  anthropic:
    base_url: https://api.anthropic.com
    keys:
      - key: sk-ant-xxx
        active: true
""")
    rotator = KeyRotator(config)
    addon = TelemetryAddon(logger, config, rotator)

    flow = _make_flow(url="https://api.anthropic.com/v1/messages")
    flow.request.host = "api.anthropic.com"
    addon.request(flow)
    assert flow.request.headers["x-api-key"] == "sk-ant-xxx"


def test_addon_rotates_keys_round_robin(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
      - key: sk-b
        active: true
      - key: sk-c
        active: true
""")
    keys_seen = []
    for _ in range(6):
        flow = _make_flow()
        flow.request.host = "api.openai.com"
        addon.request(flow)
        keys_seen.append(flow.request.headers["Authorization"])
    assert keys_seen == [
        "Bearer sk-a", "Bearer sk-b", "Bearer sk-c",
        "Bearer sk-a", "Bearer sk-b", "Bearer sk-c",
    ]


def test_addon_skips_inactive_keys(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
      - key: sk-b
        active: false
      - key: sk-c
        active: true
""")
    keys_seen = []
    for _ in range(4):
        flow = _make_flow()
        flow.request.host = "api.openai.com"
        addon.request(flow)
        keys_seen.append(flow.request.headers["Authorization"])
    assert keys_seen == ["Bearer sk-a", "Bearer sk-c", "Bearer sk-a", "Bearer sk-c"]


def test_addon_no_matching_provider_no_injection(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-test
        active: true
""")
    flow = _make_flow(url="https://api.cohere.com/v1/chat")
    flow.request.host = "api.cohere.com"
    flow.request.headers = {"Authorization": "Bearer cohere-key"}
    addon.request(flow)
    assert flow.request.headers["Authorization"] == "Bearer cohere-key"


def test_addon_overrides_client_key(tmp_path):
    addon = _make_addon(tmp_path, """
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-real
        active: true
""")
    flow = _make_flow()
    flow.request.host = "api.openai.com"
    flow.request.headers = {"Authorization": "Bearer sk-dummy"}
    addon.request(flow)
    assert flow.request.headers["Authorization"] == "Bearer sk-real"


def test_addon_logs_request(tmp_path):
    db_path = tmp_path / "test.db"
    addon = _make_addon(tmp_path, """
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
""")
    flow = _make_flow()
    addon.response(flow)
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT method, request_body FROM requests").fetchone()
    conn.close()
    assert row[0] == "POST"
    assert "gpt-4" in row[1]


def test_addon_calculates_latency(tmp_path):
    db_path = tmp_path / "test.db"
    addon = _make_addon(tmp_path, """
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-a
        active: true
""")
    flow = _make_flow()
    flow.response.timestamp_start = 1000.0
    flow.response.timestamp_end = 1001.5
    addon.response(flow)
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT latency_ms FROM requests").fetchone()
    conn.close()
    assert row[0] == 1500.0


def test_addon_config_hot_reload(tmp_path):
    """Changing config file takes effect without restart."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-old
        active: true
""")
    db_path = tmp_path / "test.db"
    logger = TelemetryLogger(db_path)
    config = Config(config_file)
    rotator = KeyRotator(config)
    addon = TelemetryAddon(logger, config, rotator)

    flow = _make_flow()
    addon.request(flow)
    assert flow.request.headers["Authorization"] == "Bearer sk-old"

    # Hot reload
    config_file.write_text("""
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-old
        active: false
      - key: sk-new
        active: true
""")
    flow = _make_flow()
    addon.request(flow)
    assert flow.request.headers["Authorization"] == "Bearer sk-new"
```

**Step 3: Run tests**

```bash
uv run pytest tests/test_addon.py -v
```

Expected: 10 passed

**Step 4: Commit**

```bash
git add src/otel_agent/addon.py tests/test_addon.py
git commit -m "feat: addon uses Config + KeyRotator with hot-reload"
```

---

### Task 4: Update CLI to use config file, keep CLI args as overrides

**Objective:** Wire Config/KeyRotator into `run_proxy`, make `--upstream` and `-k` optional overrides.

**Files:**
- Modify: `src/otel_agent/proxy.py`

**Step 1: Update `run_proxy`**

```python
async def run_proxy(args):
    from mitmproxy.options import Options
    from mitmproxy.tools.dump import DumpMaster
    from otel_agent.addon import TelemetryAddon
    from otel_agent.config import Config
    from otel_agent.logger import TelemetryLogger
    from otel_agent.rotator import KeyRotator

    config_path = Path(args.config).expanduser()
    logger = TelemetryLogger(Path(args.db))
    config = Config(config_path)
    rotator = KeyRotator(config)
    addon = TelemetryAddon(
        logger, config, rotator,
        upstream_override=args.upstream,
    )

    opts = Options(listen_port=args.port)
    master = DumpMaster(opts)
    master.addons.add(addon)

    upstream_msg = f" -> {args.upstream}" if args.upstream else ""
    print(f"otel-proxy listening on :{args.port}{upstream_msg}")
    print(f"logging to {args.db}")
    print(f"config: {config_path}")

    # Show loaded providers and key counts
    for name, provider in config._providers.items():
        active = len(provider.active_keys())
        total = len(provider.keys)
        print(f"  provider: {name} ({active}/{total} keys active)")

    print("Ctrl+C to stop\n")

    try:
        await master.run()
    except KeyboardInterrupt:
        pass
    finally:
        master.shutdown()
        logger.close()
```

**Step 2: Add `--config` arg and update parser**

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="otel-proxy",
        description="LLM API telemetry proxy — intercept, log, redirect.",
    )
    sub = parser.add_subparsers(dest="command")

    # proxy command
    proxy_p = sub.add_parser("proxy", help="Run the proxy")
    proxy_p.add_argument("-p", "--port", type=int, default=8080,
                         help="Proxy listen port (default: 8080)")
    proxy_p.add_argument("-u", "--upstream", type=str, default="",
                         help="Override upstream target (overrides config base_url)")
    proxy_p.add_argument("-d", "--db", type=str, default="telemetry.db",
                         help="SQLite database path (default: telemetry.db)")
    proxy_p.add_argument("-c", "--config", type=str,
                         default="~/.otel-agent/config.yaml",
                         help="Config file path (default: ~/.otel-agent/config.yaml)")

    # view command (unchanged)
    view_p = sub.add_parser("view", help="View logged requests")
    view_p.add_argument("-d", "--db", type=str, default="telemetry.db",
                        help="SQLite database path")
    view_p.add_argument("-f", "--filter", type=str, default="",
                        help="Filter by upstream (substring match)")
    view_p.add_argument("-n", "--limit", type=int, default=20)

    return parser
```

**Step 3: Remove `parse_api_keys` function** (no longer needed, config handles it)

Delete the entire `parse_api_keys` function and the `import os` line from `proxy.py`.

**Step 4: Update proxy tests**

```python
# tests/test_proxy.py
from otel_agent.proxy import build_parser


def test_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["proxy"])
    assert args.port == 8080
    assert args.upstream == ""
    assert args.db == "telemetry.db"
    assert args.config == "~/.otel-agent/config.yaml"


def test_parser_custom_values():
    parser = build_parser()
    args = parser.parse_args([
        "proxy", "--port", "9090",
        "--upstream", "https://api.anthropic.com",
        "--db", "/tmp/logs.db",
        "--config", "/tmp/my-config.yaml",
    ])
    assert args.port == 9090
    assert args.upstream == "https://api.anthropic.com"
    assert args.db == "/tmp/logs.db"
    assert args.config == "/tmp/my-config.yaml"


def test_parser_view_subcommand():
    parser = build_parser()
    args = parser.parse_args(["view", "--filter", "openai", "--limit", "50"])
    assert args.command == "view"
    assert args.filter == "openai"
    assert args.limit == 50
```

**Step 5: Run all tests**

```bash
uv run pytest tests/ -v -m "not integration"
```

Expected: all passed

**Step 6: Commit**

```bash
git add src/otel_agent/proxy.py tests/test_proxy.py
git commit -m "feat: CLI uses config file, remove parse_api_keys"
```

---

### Task 5: Create default config file generator

**Objective:** Add an `otel-agent init` subcommand that creates `~/.otel-agent/config.yaml` with a template.

**Files:**
- Modify: `src/otel_agent/proxy.py` (add `init` subcommand)

**Step 1: Add `init` subcommand to parser**

```python
    # init command
    init_p = sub.add_parser("init", help="Create default config file")
    init_p.add_argument("-c", "--config", type=str,
                        default="~/.otel-agent/config.yaml",
                        help="Config file path")
```

**Step 2: Add init handler to main()**

```python
    if args.command == "init":
        from otel_agent.config import DEFAULT_CONFIG
        config_path = Path(args.config).expanduser()
        if config_path.exists():
            print(f"Config already exists: {config_path}")
            print("Edit it manually or delete it to regenerate.")
        else:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(DEFAULT_CONFIG)
            print(f"Created config: {config_path}")
            print("Edit it to add your API keys.")
```

**Step 3: Add DEFAULT_CONFIG to config.py**

```python
# At the top of src/otel_agent/config.py
DEFAULT_CONFIG = """\
# otel-agent configuration
# Docs: https://github.com/your-org/otel-agent

providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: YOUR_OPENAI_API_KEY
        active: true
      # Add more keys to rotate:
      # - key: YOUR_SECOND_KEY
      #   active: true

  anthropic:
    base_url: https://api.anthropic.com
    keys:
      - key: YOUR_ANTHROPIC_API_KEY
        active: true
"""
```

**Step 4: Test manually**

```bash
uv run otel-agent init -c /tmp/test-config.yaml
cat /tmp/test-config.yaml
rm /tmp/test-config.yaml
```

Expected: YAML template printed

**Step 5: Run all tests**

```bash
uv run pytest tests/ -v -m "not integration"
```

Expected: all passed

**Step 6: Commit**

```bash
git add src/otel_agent/proxy.py src/otel_agent/config.py
git commit -m "feat: otel-agent init subcommand generates default config"
```

---

### Task 6: Update README

**Objective:** Document the new config-driven workflow.

**Files:**
- Modify: `README.md`

**Step 1: Rewrite README**

```markdown
# otel-agent — LLM Telemetry Proxy

Intercept, log, and redirect LLM API calls. Config-driven multi-key rotation.

## Quick Start

```bash
uv sync
uv run otel-agent init       # creates ~/.otel-agent/config.yaml
# edit config to add your keys
uv run otel-proxy proxy      # start proxy on :8080
```

## Config File

`~/.otel-agent/config.yaml`:

```yaml
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-proj-key1
        active: true
      - key: sk-proj-key2
        active: true
      - key: sk-proj-key3
        active: false   # disabled

  anthropic:
    base_url: https://api.anthropic.com
    keys:
      - key: sk-ant-key1
        active: true
```

- **Round-robin** among active keys per provider
- **Hot-reload**: edit the file, changes take effect on next request (no restart)
- Toggle `active: true/false` to enable/disable keys

## Usage

```bash
# Start proxy
uv run otel-proxy proxy

# Custom port and DB
uv run otel-proxy proxy -p 9090 -d /tmp/logs.db

# Override upstream (ignores config base_url)
uv run otel-proxy proxy -u https://custom-endpoint.com

# Use different config file
uv run otel-proxy proxy -c ./project-config.yaml

# View logged requests
uv run otel-proxy view
uv run otel-proxy view -f openai -n 50
```

## Client Usage

No API key needed in client — proxy injects it:

```python
from openai import OpenAI
import httpx

client = OpenAI(
    api_key="dummy",
    http_client=httpx.Client(proxies="http://127.0.0.1:8080", verify=False),
)
```

## License

MIT
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README for config-driven workflow"
```

---

## Files Changed

| File | Action |
|------|--------|
| `pyproject.toml` | Add `pyyaml` dependency |
| `src/otel_agent/config.py` | **NEW** — Config loader with hot-reload |
| `src/otel_agent/rotator.py` | **NEW** — Round-robin key rotation |
| `src/otel_agent/addon.py` | Rewrite to use Config/KeyRotator |
| `src/otel_agent/proxy.py` | Add `--config` arg, `init` subcommand, remove `parse_api_keys` |
| `tests/test_config.py` | **NEW** — 6 tests |
| `tests/test_rotator.py` | **NEW** — 4 tests |
| `tests/test_addon.py` | Rewrite — 10 tests |
| `tests/test_proxy.py` | Simplify — 3 tests |
| `README.md` | Rewrite for config-driven workflow |

## Risks

- **File I/O per request**: Config reload checks `st_mtime` — one `stat()` syscall per request, negligible overhead
- **Thread safety**: mitmproxy is single-threaded event loop, so no lock needed for rotator indices
- **YAML parsing on change**: Only re-parses when mtime changes, not every request

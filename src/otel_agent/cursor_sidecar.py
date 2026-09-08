"""Lifecycle for the local Cursor OpenAI sidecar (cursor-agent-api)."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from otel_agent.config import Config, Provider
from otel_agent.process import (
    CURSOR_SIDECAR_LOG_FILE,
    CURSOR_SIDECAR_PORT_FILE,
    cleanup_cursor_sidecar_pid,
    ensure_agent_dir,
    get_cursor_sidecar_status,
    stop_cursor_sidecar as stop_tracked_sidecar,
    write_cursor_sidecar_pid,
)

DEFAULT_SIDECAR_PORT = 4646
CURSOR_PROVIDER_NAME = "cursor"


def parse_agent_list_models(text: str) -> list[str]:
    """Parse `agent --list-models` stdout into CLI model ids."""
    ids: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("available models"):
            continue
        token = line.split(" - ", 1)[0].strip()
        if not token or " " in token:
            continue
        ids.append(token)
    return ids


def list_cursor_cli_models(*, api_key: str = "") -> list[str]:
    """Run `agent --list-models` and return CLI ids. Empty on failure."""
    binary = shutil.which("agent")
    if not binary:
        return []
    env = os.environ.copy()
    if api_key:
        env["CURSOR_API_KEY"] = api_key
    try:
        proc = subprocess.run(
            [binary, "--list-models"],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    text = proc.stdout or proc.stderr or ""
    return parse_agent_list_models(text)


# cursor-agent-api-proxy extractModel() maps unknown ids to "auto", but
# `cursor-<id>` remainder is passed through even when not in its catalog.
_SIDECAR_KNOWN_MODELS = frozenset({
    "auto",
    "composer-1.5",
    "composer-1",
    "gpt-5.3-codex",
    "gpt-5.3-codex-low",
    "gpt-5.3-codex-high",
    "gpt-5.3-codex-xhigh",
    "gpt-5.3-codex-fast",
    "gpt-5.3-codex-low-fast",
    "gpt-5.3-codex-high-fast",
    "gpt-5.3-codex-xhigh-fast",
    "gpt-5.2",
    "gpt-5.2-codex",
    "gpt-5.2-codex-high",
    "gpt-5.2-codex-low",
    "gpt-5.2-codex-xhigh",
    "gpt-5.2-codex-fast",
    "gpt-5.2-codex-high-fast",
    "gpt-5.2-codex-low-fast",
    "gpt-5.2-codex-xhigh-fast",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex-max-high",
    "opus-4.6-thinking",
    "sonnet-4.5-thinking",
    "gpt-5.2-high",
    "opus-4.6",
    "opus-4.5",
    "opus-4.5-thinking",
    "sonnet-4.5",
    "gpt-5.1-high",
    "gemini-3-pro",
    "gemini-3-flash",
    "grok",
})


def cursor_cli_model_for_sidecar(cli_id: str) -> str:
    """Rewrite a CLI id so cursor-agent-api-proxy will not coerce it to auto."""
    if not cli_id or cli_id in _SIDECAR_KNOWN_MODELS or cli_id.startswith("cursor-"):
        return cli_id
    return f"cursor-{cli_id}"


def cursor_provider(config: Config) -> Provider | None:
    """Return the Cursor provider row when it points at a loopback sidecar."""
    provider = config.get_provider(CURSOR_PROVIDER_NAME)
    if provider is None:
        return None
    host = (urlparse(provider.base_url).hostname or "").lower()
    if host not in ("127.0.0.1", "localhost"):
        return None
    return provider


def sidecar_port(provider: Provider) -> int:
    parsed = urlparse(provider.base_url)
    if parsed.port:
        return parsed.port
    return DEFAULT_SIDECAR_PORT


def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def start_cursor_sidecar(config: Config) -> dict | None:
    """Start cursor-agent-api when a loopback Cursor provider exists.

    Returns {pid, port} when this process spawned the sidecar, {pid, port,
    adopted: True} when one was already listening, or None when no Cursor
    sidecar is configured. Missing CLI / binary prints a warning and returns
    None (proxy still starts).
    """
    provider = cursor_provider(config)
    if provider is None:
        return None

    port = sidecar_port(provider)
    status = get_cursor_sidecar_status()
    if status is not None:
        return status

    if _is_port_in_use(port):
        return {"pid": 0, "port": port, "adopted": True}

    binary = shutil.which("cursor-agent-api")
    if not binary:
        print("Cursor sidecar skipped: cursor-agent-api not on PATH.")
        print("  Install: npm install -g cursor-agent-api-proxy")
        return None
    if not shutil.which("agent"):
        print("Cursor sidecar skipped: Cursor CLI `agent` not on PATH.")
        print("  Install: curl https://cursor.com/install -fsS | bash")
        return None

    env = os.environ.copy()
    if provider.api_key:
        env.setdefault("CURSOR_API_KEY", provider.api_key)

    ensure_agent_dir()
    log_fd = open(CURSOR_SIDECAR_LOG_FILE, "a")
    proc = subprocess.Popen(
        [binary, "run", str(port)],
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env,
    )
    write_cursor_sidecar_pid(proc.pid)
    CURSOR_SIDECAR_PORT_FILE.write_text(str(port))
    time.sleep(0.5)
    if proc.poll() is not None:
        cleanup_cursor_sidecar_pid()
        print("Cursor sidecar failed to start. Check ~/.otel-agent/cursor-sidecar.log")
        return None
    return {"pid": proc.pid, "port": port}


def stop_cursor_sidecar() -> bool:
    """Stop the sidecar this gateway started. Leaves an adopted process running."""
    return stop_tracked_sidecar()

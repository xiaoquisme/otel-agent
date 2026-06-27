"""Process management for background proxy daemon."""

from __future__ import annotations

import os
import signal
from pathlib import Path

AGENT_DIR = Path.home() / ".otel-agent"
PID_FILE = AGENT_DIR / "proxy.pid"
PORT_FILE = AGENT_DIR / "proxy.port"
LOG_FILE = AGENT_DIR / "proxy.log"


def ensure_agent_dir() -> Path:
    """Create ~/.otel-agent/ if it doesn't exist. Returns the path."""
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    return AGENT_DIR


def write_pid(pid: int) -> None:
    """Write PID to the PID file."""
    ensure_agent_dir()
    PID_FILE.write_text(str(pid))


def read_pid() -> int | None:
    """Read PID from file. Returns None if missing or invalid."""
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def is_running(pid: int) -> bool:
    """Check if a process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def get_proxy_status() -> dict | None:
    """Get proxy status. Returns {"pid": int, "port": int} or None."""
    pid = read_pid()
    if pid is None:
        return None
    if not is_running(pid):
        cleanup_pid()
        return None
    port = 8080
    if PORT_FILE.exists():
        try:
            port = int(PORT_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    return {"pid": pid, "port": port}


def cleanup_pid() -> None:
    """Delete the PID and port files."""
    for f in (PID_FILE, PORT_FILE):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass


def stop_proxy(timeout: float = 5.0) -> bool:
    """Send SIGTERM to the proxy process and wait for it to exit.

    Returns True if proxy was stopped, False if no proxy was running.
    """
    pid = read_pid()
    if pid is None or not is_running(pid):
        cleanup_pid()
        return False

    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        cleanup_pid()
        return False

    # Wait for process to exit
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_running(pid):
            cleanup_pid()
            return True
        time.sleep(0.1)

    # Force kill if still alive
    try:
        os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    cleanup_pid()
    return True

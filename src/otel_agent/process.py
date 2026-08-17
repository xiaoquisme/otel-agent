"""Process management for background daemons (proxy, dashboard)."""

from __future__ import annotations

import os
import signal
from pathlib import Path

AGENT_DIR = Path.home() / ".otel-agent"
PID_FILE = AGENT_DIR / "proxy.pid"
PORT_FILE = AGENT_DIR / "proxy.port"
LOG_FILE = AGENT_DIR / "proxy.log"

DASHBOARD_PID_FILE = AGENT_DIR / "dashboard.pid"
DASHBOARD_PORT_FILE = AGENT_DIR / "dashboard.port"
DASHBOARD_LOG_FILE = AGENT_DIR / "dashboard.log"


def ensure_agent_dir() -> Path:
    """Create ~/.otel-agent/ if it doesn't exist. Returns the path."""
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    return AGENT_DIR


def _write_pid(pid_file: Path, pid: int) -> None:
    ensure_agent_dir()
    pid_file.write_text(str(pid))


def _read_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def write_pid(pid: int) -> None:
    """Write PID to the proxy PID file."""
    _write_pid(PID_FILE, pid)


def read_pid() -> int | None:
    """Read proxy PID from file. Returns None if missing or invalid."""
    return _read_pid(PID_FILE)


def write_dashboard_pid(pid: int) -> None:
    """Write PID to the dashboard PID file."""
    _write_pid(DASHBOARD_PID_FILE, pid)


def read_dashboard_pid() -> int | None:
    """Read dashboard PID from file. Returns None if missing or invalid."""
    return _read_pid(DASHBOARD_PID_FILE)


def is_running(pid: int) -> bool:
    """Check if a process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _get_status(pid_file: Path, port_file: Path, default_port: int) -> dict | None:
    pid = _read_pid(pid_file)
    if pid is None:
        return None
    if not is_running(pid):
        _cleanup(pid_file, port_file)
        return None
    port = default_port
    if port_file.exists():
        try:
            port = int(port_file.read_text().strip())
        except (ValueError, OSError):
            pass
    return {"pid": pid, "port": port}


def get_proxy_status() -> dict | None:
    """Get proxy status. Returns {"pid": int, "port": int} or None."""
    return _get_status(PID_FILE, PORT_FILE, 45638)


def get_dashboard_status() -> dict | None:
    """Get dashboard status. Returns {"pid": int, "port": int} or None."""
    return _get_status(DASHBOARD_PID_FILE, DASHBOARD_PORT_FILE, 9090)


def _cleanup(*files: Path) -> None:
    for f in files:
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass


def cleanup_pid() -> None:
    """Delete the proxy PID and port files."""
    _cleanup(PID_FILE, PORT_FILE)


def cleanup_dashboard_pid() -> None:
    """Delete the dashboard PID and port files."""
    _cleanup(DASHBOARD_PID_FILE, DASHBOARD_PORT_FILE)


def _stop(pid_file: Path, port_file: Path, timeout: float = 5.0) -> bool:
    pid = _read_pid(pid_file)
    if pid is None or not is_running(pid):
        _cleanup(pid_file, port_file)
        return False

    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        _cleanup(pid_file, port_file)
        return False

    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_running(pid):
            _cleanup(pid_file, port_file)
            return True
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    _cleanup(pid_file, port_file)
    return True


def stop_proxy(timeout: float = 5.0) -> bool:
    """Send SIGTERM to the proxy process and wait for it to exit.

    Returns True if proxy was stopped, False if no proxy was running.
    """
    return _stop(PID_FILE, PORT_FILE, timeout)


def stop_dashboard(timeout: float = 5.0) -> bool:
    """Send SIGTERM to the dashboard process and wait for it to exit.

    Returns True if dashboard was stopped, False if no dashboard was running.
    """
    return _stop(DASHBOARD_PID_FILE, DASHBOARD_PORT_FILE, timeout)

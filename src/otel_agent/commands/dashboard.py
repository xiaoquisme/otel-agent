"""otel-agent dashboard subcommand.

Starts a standalone dashboard server using FastAPI (with only the dashboard
routes).  When the proxy is running, the dashboard is already served at the
proxy's root URL — use ``otel-agent proxy`` instead.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

from otel_agent.process import (
    DASHBOARD_LOG_FILE,
    DASHBOARD_PORT_FILE,
    cleanup_dashboard_pid,
    ensure_agent_dir,
    get_dashboard_status,
    stop_dashboard,
    write_dashboard_pid,
)


def handle_dashboard(args) -> None:
    """Dispatch dashboard subcommand."""
    action = getattr(args, "dashboard_action", None)
    if action == "stop":
        handle_dashboard_stop(args)
    elif action == "status":
        handle_dashboard_status(args)
    elif action == "logs":
        handle_dashboard_logs(args)
    else:
        handle_dashboard_start(args)


def _is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def handle_dashboard_start(args) -> None:
    """Start the dashboard (background or foreground)."""
    if getattr(args, "foreground", False):
        _run_foreground(args)
        return

    db_path = Path(args.db).expanduser()
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Start the proxy first: otel-agent proxy")
        return

    status = get_dashboard_status()
    if status is not None:
        print(f"Dashboard already running (PID {status['pid']}).")
        print("Use 'otel-agent dashboard stop' to stop it first.")
        sys.exit(1)

    if _is_port_in_use(args.port):
        print(f"Port {args.port} is already in use. Try: otel-agent dashboard -p 9091")
        sys.exit(1)

    ensure_agent_dir()
    log_fd = open(DASHBOARD_LOG_FILE, "a")

    cmd = [
        sys.executable, "-m", "otel_agent",
        "dashboard", "--foreground",
        "-p", str(args.port),
        "-d", str(db_path),
    ]
    proxy_port = getattr(args, "proxy", None)
    if proxy_port:
        cmd.extend(["--proxy", str(proxy_port)])

    proc = subprocess.Popen(
        cmd,
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    write_dashboard_pid(proc.pid)
    DASHBOARD_PORT_FILE.write_text(str(args.port))

    time.sleep(0.5)
    if proc.poll() is not None:
        cleanup_dashboard_pid()
        print("Dashboard failed to start. Check logs: otel-agent dashboard logs")
        sys.exit(1)

    print(f"Dashboard started at http://localhost:{args.port} (PID {proc.pid})")
    print(f"Logging to {DASHBOARD_LOG_FILE}")


def _run_foreground(args) -> None:
    """Run the dashboard server in the foreground (blocking)."""
    from fastapi import FastAPI
    import uvicorn

    from otel_agent.dashboard.api import DashboardAPI
    from otel_agent.dashboard.routes import router as dashboard_router, set_api as set_dashboard_api
    from otel_agent.dashboard.spa import find_frontend_dist, register_frontend, register_legacy_index

    _pkg_dir = Path(__file__).parent
    frontend_dist = find_frontend_dist(
        _pkg_dir.parent / "dashboard" / "frontend_dist",
        _pkg_dir.parent.parent.parent / "frontend" / "dist",
    )

    db_path = Path(args.db).expanduser()
    port = args.port

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Start the proxy first: otel-agent proxy")
        return

    app = FastAPI(title="otel-agent-dashboard", version="0.1.0")

    proxy_port = getattr(args, "proxy", None)
    dashboard_api = DashboardAPI(db_path, proxy_port=proxy_port)
    set_dashboard_api(dashboard_api)
    app.include_router(dashboard_router)
    register_frontend(app, frontend_dist)
    if frontend_dist is None:
        register_legacy_index(app, Path(__file__).parent.parent / "dashboard" / "index.html")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        dashboard_api.close()

    print(f"Dashboard running at http://localhost:{port}")
    print(f"Database: {db_path}")
    if proxy_port:
        print(f"Proxy: http://127.0.0.1:{proxy_port}")
    else:
        print("Note: No --proxy specified. Direct SQLite access used.")
        print("If proxy is running, use --proxy <port> to avoid lock conflicts.")
    print("Ctrl+C to stop\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def handle_dashboard_stop(args) -> None:
    """Stop the running dashboard."""
    stopped = stop_dashboard()
    if stopped:
        print("Dashboard stopped.")
    else:
        print("No dashboard is running.")


def handle_dashboard_status(args) -> None:
    """Show dashboard status."""
    status = get_dashboard_status()
    if status is not None:
        print(f"Dashboard running on :{status['port']} (PID {status['pid']})")
    else:
        print("Dashboard is not running.")


def handle_dashboard_logs(args) -> None:
    """Show dashboard logs."""
    if not get_dashboard_status() and not DASHBOARD_LOG_FILE.exists():
        print("No dashboard is running and no logs found.")
        return

    follow = getattr(args, "follow", False)
    lines = getattr(args, "lines", 50)

    if follow:
        _follow_logs()
    else:
        _show_logs(lines)


def _show_logs(n: int = 50) -> None:
    """Show last N lines of the log file."""
    if not DASHBOARD_LOG_FILE.exists():
        print("No log file found.")
        return
    with open(DASHBOARD_LOG_FILE) as f:
        all_lines = f.readlines()
        for line in all_lines[-n:]:
            print(line, end="")


def _follow_logs() -> None:
    """Stream log file in real-time (like tail -f)."""
    if not DASHBOARD_LOG_FILE.exists():
        print("No log file found.")
        return
    print(f"Following {DASHBOARD_LOG_FILE} (Ctrl+C to stop)\n")
    try:
        with open(DASHBOARD_LOG_FILE) as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    print(line, end="")
                else:
                    time.sleep(0.1)
    except KeyboardInterrupt:
        pass

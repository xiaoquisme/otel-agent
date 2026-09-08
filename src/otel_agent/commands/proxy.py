"""otel-agent proxy subcommand group — manages the FastAPI/uvicorn gateway."""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from otel_agent.process import (
    LOG_FILE,
    PID_FILE,
    PORT_FILE,
    cleanup_pid,
    ensure_agent_dir,
    get_proxy_status,
    is_running,
    read_pid,
    stop_proxy,
    write_pid,
)
from otel_agent.cursor_sidecar import start_cursor_sidecar, stop_cursor_sidecar


def handle_proxy(args) -> None:
    """Dispatch proxy subcommand."""
    action = getattr(args, "proxy_action", "start")
    if action == "start":
        handle_proxy_start(args)
    elif action == "stop":
        handle_proxy_stop(args)
    elif action == "restart":
        handle_proxy_restart(args)
    elif action == "status":
        handle_proxy_status(args)
    elif action == "logs":
        handle_proxy_logs(args)
    else:
        handle_proxy_start(args)


def _is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def handle_proxy_start(args) -> None:
    """Start the gateway (background or foreground)."""
    foreground = getattr(args, "foreground", False)

    if foreground:
        _run_foreground(args)
        return

    # Check if already running
    status = get_proxy_status()
    if status is not None:
        print(f"Gateway already running (PID {status['pid']}).")
        print("Use 'otel-agent proxy stop' to stop it first.")
        sys.exit(1)

    # Check if port is in use
    if _is_port_in_use(args.port):
        print(f"Port {args.port} is already in use. Try: otel-agent proxy -p 9090")
        sys.exit(1)

    # Start background process
    ensure_agent_dir()
    log_fd = open(LOG_FILE, "a")

    # Build the command to re-run in foreground mode
    cmd = [
        sys.executable, "-m", "otel_agent",
        "proxy", "--foreground",
        "-p", str(args.port),
        "-d", str(Path(args.db).expanduser()),
        "-c", str(Path(args.config).expanduser()),
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    write_pid(proc.pid)
    PORT_FILE.write_text(str(args.port))

    # Wait a moment to verify it started
    time.sleep(0.5)
    if proc.poll() is not None:
        cleanup_pid()
        print("Gateway failed to start. Check logs: otel-agent proxy logs")
        sys.exit(1)

    print(f"Gateway started on :{args.port} (PID {proc.pid})")
    print(f"Logging to {LOG_FILE}")

    from otel_agent.config import Config

    sidecar = start_cursor_sidecar(Config(Path(args.config).expanduser()))
    if sidecar:
        extra = " (already listening)" if sidecar.get("adopted") else f" (PID {sidecar['pid']})"
        print(f"Cursor sidecar on :{sidecar['port']}{extra}")


def _run_foreground(args) -> None:
    """Run the gateway in the foreground (blocking)."""
    _run_server(args)


def _run_server(args) -> None:
    """Run the uvicorn server."""
    import uvicorn

    from otel_agent.config import Config
    from otel_agent.logger import TelemetryLogger
    from otel_agent.server import create_app

    config_path = Path(args.config).expanduser()
    config = Config(config_path)
    logger = TelemetryLogger(Path(args.db).expanduser(), backend=config.storage)
    app = create_app(config, logger)

    print(f"otel-agent gateway listening on :{args.port}")
    print(f"logging to {args.db}")
    print(f"config: {config_path}")

    for name, provider in config.providers.items():
        print(f"  {name}: {provider.base_url} ({provider.api_format})")

    print(f"\nEndpoints:")
    print(f"  POST /v1/chat/completions  (OpenAI format)")
    print(f"  POST /v1/messages          (Anthropic format)")
    print(f"  GET  /v1/models            (list available models)")
    print(f"  GET  /health")
    print(f"\nCtrl+C to stop\n")

    sidecar = start_cursor_sidecar(config)
    if sidecar:
        extra = " (already listening)" if sidecar.get("adopted") else f" (PID {sidecar['pid']})"
        print(f"Cursor sidecar on :{sidecar['port']}{extra}")

    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=args.port,
            log_level="info",
        )
    finally:
        stop_cursor_sidecar()


def handle_proxy_stop(args) -> None:
    """Stop the running gateway."""
    sidecar_stopped = stop_cursor_sidecar()
    stopped = stop_proxy()
    if stopped:
        print("Gateway stopped.")
    else:
        print("No gateway is running.")
    if sidecar_stopped:
        print("Cursor sidecar stopped.")


def handle_proxy_restart(args) -> None:
    """Stop and restart the gateway."""
    sidecar_stopped = stop_cursor_sidecar()
    stopped = stop_proxy()
    if stopped:
        print("Gateway stopped.")
    else:
        print("No gateway was running.")
    if sidecar_stopped:
        print("Cursor sidecar stopped.")

    # Small delay to let the port free up
    time.sleep(0.5)
    handle_proxy_start(args)


def handle_proxy_status(args) -> None:
    """Show gateway status."""
    status = get_proxy_status()
    if status is not None:
        print(f"Gateway running on :{status['port']} (PID {status['pid']})")
    else:
        print("Gateway is not running.")
    from otel_agent.process import get_cursor_sidecar_status

    sidecar = get_cursor_sidecar_status()
    if sidecar is not None:
        print(f"Cursor sidecar on :{sidecar['port']} (PID {sidecar['pid']})")


def handle_proxy_logs(args) -> None:
    """Show gateway logs."""
    if not get_proxy_status() and not LOG_FILE.exists():
        print("No gateway is running and no logs found.")
        return

    follow = getattr(args, "follow", False)
    lines = getattr(args, "lines", 50)

    if follow:
        _follow_logs()
    else:
        _show_logs(lines)


def _show_logs(n: int = 50) -> None:
    """Show last N lines of the log file."""
    if not LOG_FILE.exists():
        print("No log file found.")
        return
    with open(LOG_FILE) as f:
        all_lines = f.readlines()
        for line in all_lines[-n:]:
            print(line, end="")


def _follow_logs() -> None:
    """Stream log file in real-time (like tail -f)."""
    if not LOG_FILE.exists():
        print("No log file found.")
        return
    print(f"Following {LOG_FILE} (Ctrl+C to stop)\n")
    try:
        with open(LOG_FILE) as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    print(line, end="")
                else:
                    time.sleep(0.1)
    except KeyboardInterrupt:
        pass

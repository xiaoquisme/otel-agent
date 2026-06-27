"""otel-agent proxy subcommand group."""

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
    """Start the proxy (background or foreground)."""
    foreground = getattr(args, "foreground", False)

    if foreground:
        _run_foreground(args)
        return

    # Check if already running
    status = get_proxy_status()
    if status is not None:
        print(f"Proxy already running (PID {status['pid']}).")
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
        "-d", args.db,
        "-c", args.config,
    ]
    if args.upstream:
        cmd.extend(["-u", args.upstream])

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
        print("Proxy failed to start. Check logs: otel-agent proxy logs")
        sys.exit(1)

    print(f"Proxy started on :{args.port} (PID {proc.pid})")
    print(f"Logging to {LOG_FILE}")


def _run_foreground(args) -> None:
    """Run the proxy in the foreground (blocking)."""
    asyncio.run(_run_proxy(args))


async def _run_proxy(args) -> None:
    """Run the mitmproxy event loop."""
    import signal as sig

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

    # SIGTERM handler for graceful shutdown
    def _shutdown(signum, frame):
        master.shutdown()
        logger.close()

    sig.signal(sig.SIGTERM, _shutdown)

    upstream_msg = f" -> {args.upstream}" if args.upstream else ""
    print(f"otel-agent proxy listening on :{args.port}{upstream_msg}")
    print(f"logging to {args.db}")
    print(f"config: {config_path}")

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


def handle_proxy_stop(args) -> None:
    """Stop the running proxy."""
    stopped = stop_proxy()
    if stopped:
        print("Proxy stopped.")
    else:
        print("No proxy is running.")


def handle_proxy_restart(args) -> None:
    """Stop and restart the proxy."""
    stopped = stop_proxy()
    if stopped:
        print("Proxy stopped.")
    else:
        print("No proxy was running.")

    # Small delay to let the port free up
    time.sleep(0.5)
    handle_proxy_start(args)


def handle_proxy_status(args) -> None:
    """Show proxy status."""
    status = get_proxy_status()
    if status is not None:
        print(f"Proxy running on :{status['port']} (PID {status['pid']})")
    else:
        print("Proxy is not running.")


def handle_proxy_logs(args) -> None:
    """Show proxy logs."""
    if not get_proxy_status() and not LOG_FILE.exists():
        print("No proxy is running and no logs found.")
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
            # Seek to end
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    print(line, end="")
                else:
                    time.sleep(0.1)
    except KeyboardInterrupt:
        pass

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
    LIFECYCLE_CRASH_FILE,
    LIFECYCLE_FILE,
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


#: `proxy.log` grows one line per request; without a ceiling it becomes the
#: biggest thing in the directory and drowns the few lines worth reading.
MAX_LOG_BYTES = 20 * 1024 * 1024


def _append_log_line(message: str) -> None:
    """Write one timestamped line to `proxy.log` outside the child's stream."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        ensure_agent_dir()
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {message}\n")
    except OSError:
        pass


def _report_previous_session(previous: dict | None) -> None:
    """Conclude an unfinished session and make one readable line of it."""
    from otel_agent import lifecycle

    if previous is None or previous.get("ended"):
        return
    lifecycle.record_unclean_exit(previous)
    heartbeat = previous.get("last_heartbeat") or {}
    when = previous.get("last_heartbeat_at") or "never"
    uptime = heartbeat.get("uptime_seconds")
    rss = heartbeat.get("rss_peak_mb")
    detail = f"last heartbeat {when}"
    if uptime is not None:
        detail += f", uptime {uptime}s"
    if rss is not None:
        detail += f", peak RSS {rss}MB"
    _append_log_line(
        f"previous gateway (PID {previous.get('pid')}) exited without a shutdown "
        f"record — {detail}"
    )


def _prepare_start(args) -> None:
    """Judge the last run, then keep both logs bounded before starting a new one."""
    from otel_agent import lifecycle

    ensure_agent_dir()
    # Read before rotating: rotating first would move the very events whose
    # absence is the thing we are reporting.
    _report_previous_session(lifecycle.summarize_last_session())
    lifecycle.rotate_if_needed(LIFECYCLE_FILE)
    lifecycle.rotate_if_needed(LOG_FILE, max_bytes=MAX_LOG_BYTES)


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
    _prepare_start(args)
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
        # The child writes to a file, so Python would block-buffer its output
        # and an abrupt exit would take the last lines with it — exactly the
        # lines someone reads afterwards.
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
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


#: uvicorn answers with no timestamps by default, which makes "when did this
#: stop" unanswerable from the log alone.
UVICORN_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(asctime)s %(levelname)s %(message)s",
            "use_colors": False,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(asctime)s %(levelname)s %(client_addr)s - "%(request_line)s" %(status_code)s',
            "use_colors": False,
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {
            "handlers": ["access"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


def _enable_crash_capture(session) -> None:
    """Record an uncaught exception, and let a native crash dump its stack."""
    import faulthandler
    import sys
    import threading
    import traceback

    from otel_agent import lifecycle

    try:
        crash_stream = open(LIFECYCLE_CRASH_FILE, "a", buffering=1, encoding="utf-8")
    except OSError as exc:
        _append_log_line(f"crash log unavailable ({exc}); native crash stacks will be lost")
        crash_stream = None
    if crash_stream is not None:
        # Kept alive for the process lifetime on purpose: faulthandler writes
        # through this object when the interpreter is already dying.
        faulthandler.enable(file=crash_stream, all_threads=True)
        session.crash_stream = crash_stream

    default_excepthook = sys.excepthook

    def _excepthook(exc_type, exc, tb):
        lifecycle.append_event(
            "end",
            reason="uncaught_exception",
            error=f"{exc_type.__name__}: {exc}",
        )
        traceback.print_exception(exc_type, exc, tb)
        default_excepthook(exc_type, exc, tb)

    sys.excepthook = _excepthook

    default_thread_hook = threading.excepthook

    def _thread_excepthook(hook_args):
        lifecycle.append_event(
            "end",
            reason="uncaught_exception",
            thread=getattr(hook_args.thread, "name", None),
            error=f"{hook_args.exc_type.__name__}: {hook_args.exc_value}",
        )
        default_thread_hook(hook_args)

    threading.excepthook = _thread_excepthook


def _run_server(args) -> None:
    """Run the uvicorn server."""
    import atexit

    import uvicorn

    from otel_agent import lifecycle, model_capabilities
    from otel_agent.config import Config
    from otel_agent.logger import TelemetryLogger
    from otel_agent.server import create_app

    config_path = Path(args.config).expanduser()
    config = Config(config_path)
    logger = TelemetryLogger(Path(args.db).expanduser(), backend=config.storage)

    session = lifecycle.LifecycleSession(port=args.port, config_path=config_path)
    session.record_start()
    app = create_app(config, logger, lifecycle_session=session)
    _enable_crash_capture(session)
    atexit.register(session.record_end, "atexit")

    # Cold-start prefetch of the model capability catalog (KTD1): the first
    # /v1/models request should find the backfill table warm. Background,
    # single-flight, never blocks startup or any request path.
    model_capabilities.warm_up()

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
            log_config=UVICORN_LOG_CONFIG,
        )
    finally:
        stop_cursor_sidecar()
        session.record_end("exit")


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

    _print_last_session(status)

    from otel_agent.process import get_cursor_sidecar_status

    sidecar = get_cursor_sidecar_status()
    if sidecar is not None:
        print(f"Cursor sidecar on :{sidecar['port']} (PID {sidecar['pid']})")


def _print_last_session(status: dict | None) -> None:
    """Say what the journal knows about the last run, when that adds anything.

    A running gateway has an unfinished session by definition, so that case
    reports its heartbeat instead of an exit. Only a session whose process is
    gone while its events stop short of a terminal one is worth raising.
    """
    from otel_agent import lifecycle

    session = lifecycle.summarize_last_session()
    if session is None:
        return
    running_pid = status["pid"] if status is not None else None
    if session.get("pid") == running_pid:
        heartbeat = session.get("last_heartbeat") or {}
        uptime = heartbeat.get("uptime_seconds")
        since = f", up {uptime}s" if uptime is not None else ""
        last = session.get("last_heartbeat_at") or "not yet"
        print(f"Current session started {session.get('started_at')}{since}")
        print(f"  last heartbeat: {last}")
        return
    if session.get("ended"):
        return

    heartbeat = session.get("last_heartbeat") or {}
    print(
        f"Previous gateway (PID {session.get('pid')}) stopped without a shutdown "
        f"record."
    )
    print(f"  started:        {session.get('started_at')}")
    print(f"  last heartbeat: {session.get('last_heartbeat_at') or 'never'}")
    uptime = heartbeat.get("uptime_seconds")
    if uptime is not None:
        print(f"  ran for:        {uptime}s")
    rss = heartbeat.get("rss_peak_mb")
    if rss is not None:
        print(f"  peak RSS:       {rss}MB")
    print("  next: otel-agent proxy logs --lifecycle")


def handle_proxy_logs(args) -> None:
    """Show gateway logs."""
    if getattr(args, "lifecycle", False):
        _show_lifecycle(getattr(args, "lines", 20) or 20)
        return

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


def _format_event(event: dict) -> str:
    """Render one journal event as a single readable line."""
    ts = event.get("ts", "?")
    name = event.get("event", "?")
    detail = " ".join(
        f"{key}={value}"
        for key, value in event.items()
        if key not in ("ts", "event")
    )
    return f"{ts}  {name:<14} {detail}".rstrip()


def _show_lifecycle(n: int = 20) -> None:
    """Print the last N lifecycle events."""
    from otel_agent import lifecycle

    events = lifecycle.read_events(limit=n)
    if not events:
        print(f"No lifecycle records yet ({lifecycle.LIFECYCLE_FILE}).")
        return
    for event in events:
        print(_format_event(event))


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

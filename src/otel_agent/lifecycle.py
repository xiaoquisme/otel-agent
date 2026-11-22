"""Append-only lifecycle journal for the gateway process.

The gateway can vanish in ways no request log survives: `kill -9`, an OOM kill,
a native crash. Those leave no shutdown record, so the next start has to be the
thing that reports what happened. That is why every event is a self-contained
line appended to a plain file and flushed immediately: whatever ends the
process, the earlier lines are already on disk, and the file needs no reader to
be repaired afterwards.

Nothing here may raise. A diagnostic that fails loudly would turn "we cannot
tell why the gateway died" into "the gateway will not start".
"""

from __future__ import annotations

import asyncio
import json
import os
import resource
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from otel_agent.process import LIFECYCLE_CRASH_FILE, LIFECYCLE_FILE

#: Rotate the journal once it grows past this. A single gateway run produces a
#: start event, one heartbeat a minute, and one end event, so this holds weeks.
MAX_JOURNAL_BYTES = 1024 * 1024

#: Terminal events. A session carrying one of these is finished; a session
#: without one was cut off.
TERMINAL_EVENTS = ("end", "unclean_exit")

_WRITE_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_event(event: str, *, journal: Path | None = None, **fields: Any) -> bool:
    """Append one event line. Returns False instead of raising on failure."""
    path = Path(journal or LIFECYCLE_FILE)
    record = {"ts": _utc_now(), "event": event, "pid": os.getpid()}
    record.update(fields)
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    with _WRITE_LOCK:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
            return True
        except OSError:
            return False


def read_events(*, journal: Path | None = None, limit: int | None = None) -> list[dict]:
    """Read the journal, skipping unreadable lines. Newest events come last."""
    path = Path(journal or LIFECYCLE_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    if limit is not None and limit >= 0:
        lines = lines[-limit:]
    events: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and "event" in record:
            events.append(record)
    return events


def rotate_if_needed(path: Path | None = None, *, max_bytes: int = MAX_JOURNAL_BYTES) -> bool:
    """Rename `path` to `path.1` when it is oversized. Keeps exactly one backup."""
    target = Path(path or LIFECYCLE_FILE)
    try:
        size = target.stat().st_size
    except OSError:
        return False
    if size <= max_bytes:
        return False
    backup = target.with_name(target.name + ".1")
    try:
        backup.unlink(missing_ok=True)
        target.rename(backup)
        return True
    except OSError:
        return False


def summarize_last_session(*, journal: Path | None = None) -> dict | None:
    """Describe the most recent start event and everything after it.

    A session ends when a terminal event follows its start. When none does, the
    process was cut off — the caller decides what to report.
    """
    events = read_events(journal=journal)
    start_index = None
    for index, event in enumerate(events):
        if event.get("event") == "start":
            start_index = index
    if start_index is None:
        return None

    session = events[start_index:]
    start = session[0]
    conclusion = None
    last_heartbeat: dict | None = None
    for event in session:
        if event.get("event") == "heartbeat":
            last_heartbeat = event
        if event.get("event") in TERMINAL_EVENTS and conclusion is None:
            conclusion = event["event"]

    return {
        "pid": start.get("pid"),
        "port": start.get("port"),
        "started_at": start.get("ts"),
        "last_heartbeat_at": (last_heartbeat or {}).get("ts"),
        "last_heartbeat": last_heartbeat,
        "conclusion": conclusion,
        "ended": conclusion is not None,
    }


def count_events(event: str, *, days: int = 7, journal: Path | None = None) -> int:
    """Count `event` occurrences inside the last `days` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    total = 0
    for record in read_events(journal=journal):
        if record.get("event") != event:
            continue
        try:
            when = datetime.fromisoformat(str(record.get("ts", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if when >= cutoff:
            total += 1
    return total


def _sample() -> dict:
    """Sample what a dying process would want on record. Never raises."""
    fields: dict[str, Any] = {}
    try:
        fields["threads"] = threading.active_count()
    except Exception:
        pass
    try:
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # ru_maxrss is bytes on macOS/Darwin and kibibytes on Linux.
        divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
        fields["rss_peak_mb"] = round(peak / divisor, 1)
    except Exception:
        pass
    return fields


class LifecycleSession:
    """The current gateway run, as the journal sees it.

    Tests get an instance scoped to a temp journal; production gets the default
    one. Without an instance no journal is written at all, which is what keeps
    the app test suite out of the operator's real history.
    """

    def __init__(
        self,
        *,
        port: int = 0,
        config_path: str | Path | None = None,
        journal: Path | None = None,
        crash_file: Path | None = None,
        heartbeat_interval: float = 60.0,
    ) -> None:
        self.journal = Path(journal or LIFECYCLE_FILE)
        self.crash_file = Path(crash_file or LIFECYCLE_CRASH_FILE)
        self.pid = os.getpid()
        self.port = port
        self.config_path = str(config_path) if config_path is not None else None
        self.heartbeat_interval = heartbeat_interval
        self.started_at = _utc_now()
        self._started_monotonic = time.monotonic()
        self.last_heartbeat_at: str | None = None
        self._ended = threading.Event()

    @property
    def uptime_seconds(self) -> float:
        return round(time.monotonic() - self._started_monotonic, 1)

    def record_start(self) -> bool:
        return append_event(
            "start",
            journal=self.journal,
            port=self.port,
            version=_version(),
            config=self.config_path,
            argv=sys.argv[1:],
        )

    def record_ready(self) -> bool:
        return append_event("ready", journal=self.journal, port=self.port)

    def record_heartbeat(self) -> bool:
        fields = _sample()
        fields["uptime_seconds"] = self.uptime_seconds
        ok = append_event("heartbeat", journal=self.journal, **fields)
        if ok:
            self.last_heartbeat_at = _utc_now()
        return ok

    def record_end(self, reason: str, **extra: Any) -> bool:
        """Record the end of this run once. Later calls are no-ops."""
        if self._ended.is_set():
            return False
        self._ended.set()
        return append_event(
            "end",
            journal=self.journal,
            reason=reason,
            uptime_seconds=self.uptime_seconds,
            **extra,
        )

    async def heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            try:
                self.record_heartbeat()
            except Exception:
                # A missed sample is not a reason to lose the gateway.
                append_event("heartbeat_error", journal=self.journal)


def record_unclean_exit(previous: dict, *, journal: Path | None = None) -> bool:
    """Conclude that the session described by `previous` never finished."""
    heartbeat = previous.get("last_heartbeat") or {}
    return append_event(
        "unclean_exit",
        journal=journal,
        previous_pid=previous.get("pid"),
        started_at=previous.get("started_at"),
        last_heartbeat_at=previous.get("last_heartbeat_at"),
        uptime_seconds=heartbeat.get("uptime_seconds"),
        rss_peak_mb=heartbeat.get("rss_peak_mb"),
    )


def _version() -> str:
    from otel_agent import get_version

    return get_version()


def install_signal_journal(session: "LifecycleSession") -> "callable | None":
    """Record the signal that asked us to stop, then let the host handle it.

    Called from the app's startup hook so it lands after uvicorn installed its
    own SIGTERM/SIGINT handlers: graceful shutdown keeps working, and the
    wrapper only adds the event. Returns a restore function so a host that
    shares the process (the test client, an embedder) gets its handlers back.
    """
    import signal

    installed: list[tuple[int, object]] = []
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        previous = signal.getsignal(signum)

        def _handler(received, frame, previous=previous):
            try:
                name = signal.Signals(received).name
            except ValueError:
                name = str(received)
            session.record_end("signal", signal=name)
            if callable(previous):
                previous(received, frame)
            else:
                signal.signal(received, signal.SIG_DFL)
                os.kill(os.getpid(), received)

        try:
            signal.signal(signum, _handler)
        except (OSError, ValueError):
            # Handlers can only be installed from the main thread; a gateway
            # embedded in another host simply keeps the default behaviour.
            continue
        installed.append((signum, previous))

    def _restore() -> None:
        for signum, previous in installed:
            try:
                signal.signal(signum, previous)
            except (OSError, ValueError, TypeError):
                continue

    return _restore if installed else None

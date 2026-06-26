# Research: Background Proxy Management

**Feature**: 003-background-proxy
**Date**: 2026-06-26

## Decision 1: Process Management Approach

**Decision**: Use Python's `subprocess.Popen` with `start_new_session=True` to detach the proxy process. Store PID in `~/.otel-agent/proxy.pid`.

**Rationale**: No external dependency needed. Python stdlib handles process spawning and PID tracking. Works on Linux, macOS, and WSL.

**Alternatives considered**:
- `daemonize` library: Extra dependency for a simple use case.
- `systemd` service: Linux-only, overkill for a local dev tool.
- `nohup` shell wrapper: Fragile, hard to control from Python.
- `multiprocessing.Process` with daemon=True: Works but harder to manage PID externally.

## Decision 2: PID File Location

**Decision**: `~/.otel-agent/proxy.pid` — same directory as config.

**Rationale**: Single location for all otel-agent runtime state. Users know where to find it.

**Alternatives considered**:
- `/tmp/otel-agent.pid`: Shared tmpdir, potential conflicts with other users.
- `./.otel-agent.pid`: Per-project, confusing when running from different directories.

## Decision 3: Log File Location

**Decision**: `~/.otel-agent/proxy.log` — append mode, no rotation.

**Rationale**: Simple. Users can truncate manually if needed. No log rotation complexity for a dev tool.

**Alternatives considered**:
- Rotating logs: Overkill for a local proxy.
- Per-session logs: Naming complexity, cleanup burden.
- `/dev/null`: Loses debug info, defeats the purpose.

## Decision 4: Subcommand Structure

**Decision**: `otel-agent proxy [start|stop|restart|status|logs]` — proxy becomes a command group with subcommands. Default action (no subcommand) is `start`.

**Rationale**: Keeps all proxy lifecycle commands under one namespace. Matches user mental model ("proxy management").

**Alternatives considered**:
- Separate top-level commands (`otel-agent start`, `otel-agent stop`): Clutters top-level namespace.
- `otel-agent proxyctl`: Extra command name to remember.

## Decision 5: Foreground Mode

**Decision**: Add `--foreground` flag to `otel-agent proxy start` for debugging.

**Rationale**: Users sometimes need to see proxy output directly (debugging, development). Default is background; foreground is opt-in.

## Decision 6: Graceful Shutdown

**Decision**: Register `signal.SIGTERM` handler in the proxy process that calls `master.shutdown()` and `logger.close()`.

**Rationale**: mitmproxy's `DumpMaster` has a `shutdown()` method. Calling it ensures SQLite WAL is flushed and port is released cleanly.

---
title: "Gateway lifecycle is a recorded event, not something inferred from logs"
date: "2026-11-22"
category: "conventions"
module: "proxy"
problem_type: "convention"
component: "tooling"
severity: "medium"
symptoms:
  - "proxy.log shows a start but no shutdown, and cannot say when the process stopped"
  - "proxy status says only 'No gateway was running' after an unexplained exit"
  - "the last lines of a dying gateway were missing from proxy.log"
root_cause: "uncaptured_process_lifecycle"
resolution_type: "lifecycle_journal"
applies_when:
  - "Adding or changing the gateway's start, stop, or crash path"
  - "Debugging a gateway that disappeared without a shutdown record"
  - "Adding a new long-lived daemon next to the proxy"
tags:
  - "proxy"
  - "daemon"
  - "diagnostics"
  - "logging"
  - "lifecycle"
---

# Gateway lifecycle is a recorded event, not something inferred from logs

## Context

On 2026-11-22 the gateway stopped and nothing could say why. `~/.otel-agent/proxy.log` held the previous process's startup block and then silence: no shutdown line, no timestamps on any line, and — because the background child's stdout was block-buffered when redirected to a file — no guarantee the last lines had even reached the file. `otel-agent proxy status` reads a PID file, so once the process was gone it could only report that nothing was running. There was no `faulthandler`, so a native crash would have left no Python stack.

## Guidance

Treat "the gateway started", "it is still alive", and "here is why it stopped" as three recorded events in their own file, `~/.otel-agent/lifecycle.jsonl`:

- `start` — pid, port, version, config path, argv
- `heartbeat` — every 60s: uptime, peak RSS, thread count
- `end` — with a `reason`: the signal name, `shutdown`, `atexit`, or `uncaught_exception`

The next `proxy start` reads the tail. A `start` with no terminal event means the process was cut off, so it appends an `unclean_exit` conclusion and prints one line about it. `proxy status` surfaces the last session, `proxy logs --lifecycle` prints the journal, and `doctor` counts `unclean_exit` events in the last 7 days.

Implementation rules that make it work:

- Append and `flush` one JSON line per event. No state updates, no SQLite: at the moment a process dies it must not depend on a lock, a WAL, or a reader.
- Never let journal writes raise. A diagnostic that fails must not stop the gateway from starting.
- Install the signal wrapper from the app startup hook, after uvicorn installed its own SIGTERM/SIGINT handlers, and delegate to what was captured. Graceful shutdown stays unchanged; only the event is added.
- Run the background child with `PYTHONUNBUFFERED=1` and give uvicorn a log config with `asctime`. Rotation belongs to the parent at start time, because the child holds the parent's open fd.

## Why This Matters

Without it, every unexplained exit costs an hour of archaeology and still ends in "unknown". With it, the question "why did it close" has a first-class answer: the last heartbeat's timestamp and peak RSS bound the window and hint at a leak, the signal name separates `kill` from crash, and a stack in `lifecycle-crash.log` names a native fault.

## When to Apply

Any change to `handle_proxy_start`, `handle_proxy_stop`, `_run_server`, or the app startup/shutdown hooks. Any new daemon next to the proxy should get its own journal file rather than appending to `proxy.log`.

## Related

- `src/otel_agent/lifecycle.py` — journal, session, signal wrapper
- `src/otel_agent/commands/proxy.py` — start-path judgement, status, `logs --lifecycle`
- `src/otel_agent/server.py` — startup/shutdown hooks, `/health`
- `docs/solutions/conventions/dashboard-own-pid-files.md` — the sibling convention for per-daemon process state

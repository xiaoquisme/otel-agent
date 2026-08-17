---
title: "Standalone dashboard uses its own PID and log files"
date: "2026-08-17"
category: "conventions"
module: "dashboard"
problem_type: "convention"
component: "tooling"
severity: "medium"
applies_when:
  - "Adding or changing a background start path for otel-agent dashboard"
  - "Sharing process helpers between proxy and dashboard"
tags:
  - "dashboard"
  - "daemon"
  - "pid-file"
  - "cli"
---

# Standalone dashboard uses its own PID and log files

## Context

`otel-agent dashboard` now starts in the background by default, using the same detach model as `otel-agent proxy` (re-exec with `--foreground`, `start_new_session=True`, PID file, log append). Proxy and dashboard are expected to run at the same time.

## Guidance

Keep dashboard process state in `~/.otel-agent/dashboard.pid`, `dashboard.port`, and `dashboard.log`. Do not reuse `proxy.pid` / `proxy.port` / `proxy.log`.

When spawning the child, only pass `--proxy` if the user set a port. `--proxy` is `type=int`; a literal `None` makes argparse reject the child and the parent reports a failed start.

`otel-agent dashboard` with no subcommand remains start, so existing `-p` / `-d` / `--proxy` flags keep working. Lifecycle actions are `stop`, `status`, and `logs`.

## Why This Matters

Sharing the proxy PID file would make starting the dashboard look like the gateway is already running, or stop the wrong process. Omitting lifecycle commands after a background default leaves an orphan uvicorn with no first-party stop path.

## When to Apply

Any change to standalone dashboard process management, or any new long-lived CLI daemon next to the proxy.

## Examples

Background start writes dashboard files only:

- PID: `~/.otel-agent/dashboard.pid`
- Port: `~/.otel-agent/dashboard.port`
- Log: `~/.otel-agent/dashboard.log`

Foreground escape hatch: `otel-agent dashboard --foreground`.

## Related Issues

- `docs/solutions/architecture-patterns/dashboard-render-delegation-pattern.md` — in-proxy dashboard is a different process; this convention is only for the standalone CLI
- `src/otel_agent/process.py` — `DASHBOARD_*` file constants and `stop_dashboard`
- `src/otel_agent/commands/dashboard.py` — spawn / stop / status / logs

# Implementation Plan: Background Proxy Management

**Branch**: `003-background-proxy` | **Date**: 2026-06-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-background-proxy/spec.md`

## Summary

Add background proxy management to otel-agent. `otel-agent proxy` starts the proxy as a daemon with PID file and log file. New subcommands: `stop`, `restart`, `status`, `logs`. Add `--foreground` flag for debugging. The proxy registers a SIGTERM handler for graceful shutdown.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: mitmproxy>=10.0, pyyaml>=6.0.3 (no new deps)

**Storage**: PID file (`~/.otel-agent/proxy.pid`), log file (`~/.otel-agent/proxy.log`)

**Testing**: pytest

**Target Platform**: Linux, macOS, WSL

**Project Type**: CLI tool

**Performance Goals**: Background start <1s, stop <5s, status <1s

**Constraints**: Single instance only. Backward-compatible — `otel-agent proxy` with no args still starts proxy.

**Scale/Scope**: Single-user local tool

## Constitution Check

| Principle | Gate | Status |
| --------- | ---- | ------ |
| I. Code Quality | Single responsibility, type hints | ✅ PASS — process management in one module |
| II. Testing Standards | Unit tests for each change | ✅ PASS — tests for PID, start/stop/status |
| III. UX Consistency | --help, clear errors | ✅ PASS — subcommand help, stale PID detection |
| IV. Performance | <5ms overhead | ✅ PASS — no proxy overhead change |

No violations.

## Project Structure

### Documentation (this feature)

```text
specs/003-background-proxy/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── proxy-commands.md
└── tasks.md
```

### Source Code (files to change)

```text
src/otel_agent/
├── commands/
│   └── proxy.py         # Add start/stop/restart/status/logs handlers
├── process.py           # NEW: PID file and process management utilities
└── cli.py               # Update proxy subcommand with sub-subcommands

tests/
├── test_process.py      # NEW: PID file and process management tests
├── test_cli.py          # Update for proxy subcommands
└── test_proxy.py        # Update for proxy subcommands
```

**Structure Decision**: New `process.py` module for PID/process management (single responsibility). `proxy.py` gets subcommand handlers. `cli.py` gets argparse restructuring.

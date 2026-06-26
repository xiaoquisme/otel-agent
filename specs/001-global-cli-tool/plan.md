# Implementation Plan: Global CLI Tool

**Branch**: `001-global-cli-tool` | **Date**: 2026-06-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-global-cli-tool/spec.md`

## Summary

Restructure otel-agent from a single `otel-proxy` command into a proper CLI tool with `otel-agent` as the entry point and subcommands `init`, `proxy`, `view`, `config` (path/show/edit), and `doctor`. Add `--version` flag. Ensure installability via `uvx`, `uv tool install`, and `pip install`.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: mitmproxy>=10.0, pyyaml>=6.0.3

**Storage**: SQLite (telemetry.db), YAML (config file)

**Testing**: pytest

**Target Platform**: Linux, macOS, WSL

**Project Type**: CLI tool

**Performance Goals**: <5ms proxy overhead per request

**Constraints**: None beyond constitution principles

**Scale/Scope**: Single-user local tool

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
| --------- | ---- | ------ |
| I. Code Quality | Single responsibility per module, type hints, docstrings | ✅ PASS — each subcommand handler will be a separate function |
| II. Testing Standards | Unit tests for each subcommand, deterministic, <30s | ✅ PASS — tests will cover arg parsing and output |
| III. UX Consistency | --help on every command, sensible defaults, clear errors | ✅ PASS — this IS the feature |
| IV. Performance | No impact on proxy overhead | ✅ PASS — CLI restructuring doesn't affect proxy path |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/001-global-cli-tool/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── cli.md           # CLI contract
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/otel_agent/
├── __init__.py          # __version__ via importlib.metadata
├── __main__.py          # NEW: python -m otel_agent entry
├── cli.py               # NEW: main CLI dispatcher (argparse)
├── commands/
│   ├── __init__.py
│   ├── init.py          # otel-agent init
│   ├── proxy.py         # otel-agent proxy (moved from proxy.py)
│   ├── view.py          # otel-agent view
│   ├── config_cmd.py    # otel-agent config path|show|edit
│   └── doctor.py        # otel-agent doctor
├── config.py            # Unchanged
├── rotator.py           # Unchanged
├── addon.py             # Unchanged
├── logger.py            # Unchanged
└── viewer.py            # Unchanged

tests/
├── test_cli.py          # NEW: CLI arg parsing tests
├── test_config.py       # Unchanged
├── test_rotator.py      # Unchanged
├── test_addon.py        # Unchanged
├── test_logger.py       # Unchanged
├── test_viewer.py       # Unchanged
└── test_integration.py  # Unchanged
```

**Structure Decision**: Single project layout. The `commands/` package groups each subcommand's handler into its own module for single-responsibility. The existing `proxy.py` is split: the `build_parser` and `main` logic moves to `cli.py`, the `run_proxy` async function moves to `commands/proxy.py`.

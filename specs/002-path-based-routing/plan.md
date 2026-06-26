# Implementation Plan: Path-Based Routing

**Branch**: `002-path-based-routing` | **Date**: 2026-06-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-path-based-routing/spec.md`

## Summary

Add path-based routing to otel-agent so requests to `/openai/v1/...` route to OpenAI, `/anthropic/v1/messages` route to Anthropic, etc. The config file gains `type` and `prefix` fields per provider. The addon strips the prefix and rewrites the upstream. A new `otel-agent routes` command displays the routing table.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: mitmproxy>=10.0, pyyaml>=6.0.3 (no new deps)

**Storage**: SQLite (existing telemetry.db), YAML (config file)

**Testing**: pytest

**Target Platform**: Linux, macOS, WSL

**Project Type**: CLI tool

**Performance Goals**: <5ms proxy overhead per request (existing constitution requirement)

**Constraints**: Config backward-compatible (existing configs without `type`/`prefix` must still work)

**Scale/Scope**: Single-user local tool, typically 2-5 providers

## Constitution Check

| Principle | Gate | Status |
| --------- | ---- | ------ |
| I. Code Quality | Single responsibility, type hints, docstrings | ✅ PASS — addon gets routing logic, config gets validation |
| II. Testing Standards | Unit tests for each change, deterministic | ✅ PASS — tests for prefix matching, config validation, routing |
| III. UX Consistency | `--help`, sensible defaults, clear errors | ✅ PASS — `otel-agent routes` command, error on duplicate prefix |
| IV. Performance | <5ms overhead | ✅ PASS — prefix lookup is O(n) over ~5 providers, negligible |

No violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-path-based-routing/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── routing.md       # Routing contract
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (files to change)

```text
src/otel_agent/
├── config.py            # Add type/prefix fields, validation, route table
├── addon.py             # Add prefix matching and stripping logic
├── rotator.py           # Update to use route-based provider lookup
├── commands/
│   └── routes.py        # NEW: otel-agent routes command
└── cli.py               # Register routes subcommand

tests/
├── test_config.py       # Add tests for type/prefix/validation
├── test_addon.py        # Add tests for path routing
└── test_cli.py          # Add test for routes command
```

**Structure Decision**: Existing single-project layout. Only `config.py`, `addon.py`, `rotator.py`, `cli.py` change. One new file: `commands/routes.py`.

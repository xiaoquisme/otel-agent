# Implementation Plan: Multi-Provider Routing

**Branch**: `007-multi-provider-routing` | **Date**: 2026-06-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-multi-provider-routing/spec.md`

**Note**: This plan replaces the existing path/host routing behavior with provider-path-only routing, and introduces provider-level active selection with exactly one active provider per type.

## Summary

Replace the current routing surface with standardized provider paths `/openai` and `/anthropic`, select one active provider per type from config, and remove host/prefix fallback routing. Provider entries gain active flag validation, startup/runtime checks, and CLI visibility.

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**: mitmproxy>=10.0, pyyaml>=6.0.3
**Storage**: SQLite telemetry.db, YAML config
**Testing**: pytest
**Target Platform**: Linux, macOS, WSL
**Project Type**: CLI tool
**Performance Goals**: <5ms proxy overhead per request
**Constraints**: Remove old routing behavior; only standardized provider paths supported
**Scale/Scope**: Single-user local tool, typically small provider count

## Constitution Check

| Principle | Gate | Status |
|-----------|------|--------|
| I. Code Quality | Single responsibility, type hints, docstrings | ✅ PASS — config/model split, addon routing logic, CLI status surface |
| II. Testing Standards | Unit tests for each change, deterministic | ✅ PASS — config validation, provider lookup, active checks, routes display |
| III. UX Consistency | `--help`, sensible defaults, clear errors | ✅ PASS — startup errors, routes output, doctor/config validation |
| IV. Performance | <5ms overhead | ✅ PASS — active/provider lookup is O(n) over small provider set |

No violations.

## Project Structure

### Documentation (this feature)

```text
specs/007-multi-provider-routing/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── routing.md
└── tasks.md
```

### Source Code (files to change)

```text
src/otel_agent/
├── config.py            # Rework provider model/validation/active rules
├── addon.py             # Remove host/prefix fallback; use provider-path-only routing
├── rotator.py           # Use provider name lookup only
├── viewer.py            # Keep
├── commands/
│   ├── routes.py        # Update to active-provider-aware output
│   ├── doctor.py        # Validate active-provider rules
│   └── config_cmd.py    # Keep
└── cli.py               # Keep

tests/
├── test_config.py       # Update/add active/provider-type validation tests
├── test_addon.py        # Add provider-path-only routing tests
└── test_cli.py          # Keep
```

**Structure Decision**: Existing single-project layout. No new source files; behavior changes are replacements of old routing/validation semantics.

## Complexity Tracking

No constitution violations requiring justification.

# Research: Global CLI Tool

**Feature**: 001-global-cli-tool
**Date**: 2026-06-26

## Decision 1: CLI Framework

**Decision**: Keep `argparse` (stdlib) — no external CLI framework.

**Rationale**: The current CLI already uses `argparse` with subcommands. Adding `click` or `typer` would add a dependency for no functional gain. `argparse` supports `--version`, subcommands, and `--help` natively.

**Alternatives considered**:
- `click`: Popular but adds a dependency. Overkill for 4 subcommands.
- `typer`: Type-hint based, but still an extra dependency.
- `argparse` with `__main__.py`: Same framework, just restructure entry points.

## Decision 2: Entry Point Naming

**Decision**: Single entry point `otel-agent` with subcommands (`init`, `proxy`, `view`, `config`).

**Rationale**: The spec requires `otel-agent init`, `otel-agent proxy`, etc. Current code has `otel-proxy` as the entry point. Renaming to `otel-agent` and reorganizing subcommands under it.

**Alternatives considered**:
- Keep `otel-proxy` + add `otel-agent`: Two entry points confuse users.
- Symlink approach: Not portable across platforms.

## Decision 3: Package Name on PyPI

**Decision**: Publish as `otel-agent` on PyPI.

**Rationale**: The spec (FR-011) requires this. The `pyproject.toml` already has `name = "otel-agent"`.

**Alternatives considered**:
- `otelagent` (no hyphen): Less readable but avoids hyphen issues in some tools.
- `otel-agent-proxy`: Too long.

## Decision 4: Config Subcommand Design

**Decision**: `otel-agent config path|show|edit` as sub-subcommands.

**Rationale**: The spec (FR-008) requires `path`, `show`, and `edit` actions. `argparse` supports nested subparsers. `show` masks API keys for security. `edit` opens `$EDITOR` or falls back to `vim`.

**Alternatives considered**:
- `otel-agent config-path`, `otel-agent config-show`: Clutters top-level namespace.
- Single `otel-agent config` that opens editor: Too opinionated.

## Decision 5: Version Management

**Decision**: Read version from `pyproject.toml` at runtime via `importlib.metadata`.

**Rationale**: Single source of truth. No need to maintain `__version__` in code.

**Alternatives considered**:
- Hardcoded `__version__`: Gets out of sync.
- `setuptools-scm`: Extra dependency for git-tag-based versioning.

## Decision 6: Installation Verification

**Decision**: Add `otel-agent doctor` subcommand that checks Python version, mitmproxy availability, and config validity.

**Rationale**: Users need a way to diagnose installation issues. The spec mentions edge cases (missing uv, invalid YAML). A doctor command addresses all of them.

**Alternatives considered**:
- Inline checks at startup: Clutters every command.
- Separate diagnostic script: Not discoverable.

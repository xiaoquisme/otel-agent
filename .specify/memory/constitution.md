<!--
  Sync Impact Report
  Version change: 0.0.0 → 1.0.0 (initial ratification)
  Modified principles: N/A (first version)
  Added sections:
    - Principle I: Code Quality
    - Principle II: Testing Standards
    - Principle III: User Experience Consistency
    - Principle IV: Performance Requirements
    - Quality Gates
    - Development Workflow
  Removed sections: N/A
  Templates requiring updates:
    - .specify/templates/plan-template.md ✅ compatible (Constitution Check section exists)
    - .specify/templates/spec-template.md ✅ compatible (Success Criteria section exists)
    - .specify/templates/tasks-template.md ✅ compatible (testing phases align)
  Follow-up TODOs: none
-->

# otel-agent Constitution

## Core Principles

### I. Code Quality

All code MUST be clean, readable, and maintainable.

- Every module MUST have a single, clear responsibility.
- Functions MUST NOT exceed 50 lines. Extract helpers when logic grows.
- All public functions MUST have docstrings describing purpose, arguments, and return values.
- No dead code, commented-out code, or unused imports in committed files.
- Type hints MUST be present on all function signatures.
- Linting (ruff) MUST pass before any commit. Zero warnings, zero errors.
- Variable and function names MUST be descriptive. Single-letter names are only acceptable for loop counters and lambda parameters.

**Rationale**: A telemetry proxy is a debugging tool. If the proxy code is hard to read, users cannot trust it to handle their API traffic correctly.

### II. Testing Standards

All features MUST be tested before they are considered complete.

- Every new function MUST have at least one unit test covering the happy path.
- Every bug fix MUST include a regression test that fails before the fix and passes after.
- Tests MUST be deterministic — no reliance on network, clock, or execution order.
- Test names MUST describe the behavior being verified (e.g., `test_rotator_skips_inactive_keys`).
- Integration tests MUST cover the proxy end-to-end flow: start proxy, send request, verify logged.
- Test coverage for core modules (config, addon, rotator, logger) MUST NOT drop below 90%.
- Tests MUST run in under 30 seconds total. Slow tests MUST be marked `@pytest.mark.integration`.

**Rationale**: A proxy that silently drops or corrupts requests is worse than no proxy. Tests are the only guarantee that the system works correctly under all conditions.

### III. User Experience Consistency

CLI behavior MUST be predictable, documented, and consistent.

- Every CLI command MUST have `--help` output that describes all flags with examples.
- Default values MUST be sensible for first-time users (e.g., port 8080, config at `~/.otel-agent/config.yaml`).
- Error messages MUST include what went wrong AND what the user should do to fix it.
- Config changes MUST take effect without restart (hot-reload). If restart is required, the error message MUST say so.
- Output format MUST be consistent: startup banner shows provider/key summary, view command shows tabular data.
- The `init` command MUST NOT overwrite existing config without warning.

**Rationale**: Users adopt this proxy to reduce friction in their LLM development workflow. Inconsistent or confusing CLI behavior defeats that purpose.

### IV. Performance Requirements

The proxy MUST NOT become a bottleneck in the request path.

- Proxy overhead per request MUST NOT exceed 5ms (excluding upstream latency).
- SQLite writes MUST use WAL mode to avoid blocking concurrent reads.
- Config reload MUST check file mtime before re-parsing — no full YAML parse on every request.
- Memory usage MUST remain constant regardless of request volume (no unbounded buffers).
- Response body logging MUST handle payloads up to 10MB without crashing or excessive memory use.

**Rationale**: LLM API calls are already slow (seconds to minutes). Adding milliseconds of proxy overhead is acceptable. Adding seconds is not.

## Quality Gates

All code changes MUST pass these gates before merging:

1. **Linting**: `ruff check` passes with zero errors.
2. **Tests**: `uv run pytest tests/ -v -m "not integration"` — all pass, zero failures.
3. **Type checking**: No `Any` types in public interfaces unless explicitly justified.
4. **Config compatibility**: Existing `~/.otel-agent/config.yaml` files MUST continue to work after upgrades. Config schema changes MUST be backward-compatible or include migration guidance.
5. **Documentation**: README MUST be updated when CLI flags, config format, or behavior change.

## Development Workflow

- Commit after every logical unit of work (one feature, one fix, one refactor).
- Commit messages MUST follow conventional format: `type: description` (e.g., `feat:`, `fix:`, `docs:`, `refactor:`).
- Every PR MUST include: description of what changed, why, and how to verify.
- Breaking changes (CLI flags, config schema, log format) MUST be documented in README with migration notes.

## Governance

This constitution is the authoritative reference for otel-agent development practices. All code reviews, PRs, and architectural decisions MUST comply with these principles.

- Amendments require: documented rationale, version bump, and update to all dependent templates.
- Principle removals or redefinitions are MAJOR version changes.
- New principles or material expansions are MINOR version changes.
- Clarifications and wording fixes are PATCH version changes.
- Compliance is verified during code review. Violations MUST be justified in the PR description or fixed before merge.

**Version**: 1.0.0 | **Ratified**: 2026-06-26 | **Last Amended**: 2026-06-26

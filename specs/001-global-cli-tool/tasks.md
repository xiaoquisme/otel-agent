# Tasks: Global CLI Tool

**Input**: Design documents from `/specs/001-global-cli-tool/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/cli.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, etc.)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Project structure for new CLI layout

- [ ] T001 Create commands package directory at `src/otel_agent/commands/__init__.py`
- [ ] T002 Update `pyproject.toml` entry point from `otel-proxy = "otel_agent.proxy:main"` to `otel-agent = "otel_agent.cli:main"` and add `otel-agent = "otel_agent.cli:main"` under `[project.scripts]`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core CLI dispatcher that all subcommands depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T003 Create `src/otel_agent/__init__.py` with version helper using `importlib.metadata.version("otel-agent")`
- [ ] T004 Create `src/otel_agent/__main__.py` that calls `otel_agent.cli:main` (enables `python -m otel_agent`)
- [ ] T005 Create `src/otel_agent/cli.py` with main argparse dispatcher: top-level parser with `--version`, subcommand registration for `init`, `proxy`, `view`, `config`, `doctor`, and help text for each
- [ ] T006 Move `run_proxy` async function from `src/otel_agent/proxy.py` to `src/otel_agent/commands/proxy.py`, import it from `cli.py`
- [ ] T007 Move init handler from `src/otel_agent/proxy.py` to `src/otel_agent/commands/init.py`
- [ ] T008 Move view handler from `src/otel_agent/proxy.py` to `src/otel_agent/commands/view.py`
- [ ] T009 Delete `src/otel_agent/proxy.py` (all logic moved to cli.py + commands/)
- [ ] T010 Run `uv run pytest tests/ -v -m "not integration"` — verify all existing tests still pass after restructuring

**Checkpoint**: CLI dispatcher works, `otel-agent --help` shows all subcommands, existing tests pass

---

## Phase 3: User Story 1 — One-Command Install (P1) 🎯 MVP

**Goal**: Users can install and run `otel-agent` via `uvx`, `uv tool install`, or `pip install`.

**Independent Test**: `uvx otel-agent --version` prints version number.

### Implementation

- [ ] T011 [US1] Verify `pyproject.toml` has correct `[project.scripts]` entry: `otel-agent = "otel_agent.cli:main"` and `requires-python = ">=3.10"`
- [ ] T012 [US1] Test install with `uv pip install -e .` and run `otel-agent --version` locally

**Checkpoint**: `otel-agent` command available after install, `--version` works

---

## Phase 4: User Story 2 — First-Time Setup (P1)

**Goal**: `otel-agent init` creates a documented config file.

**Independent Test**: `otel-agent init` creates `~/.otel-agent/config.yaml` with template.

### Implementation

- [ ] T013 [US2] Create `src/otel_agent/commands/init.py` with `handle_init(args)` function that creates `~/.otel-agent/config.yaml` from `DEFAULT_CONFIG` in `config.py`, warns if exists
- [ ] T014 [US2] Register `init` subcommand in `src/otel_agent/cli.py` with `--config` flag
- [ ] T015 [P] [US2] Add test for init command in `tests/test_cli.py`: test creates config, test warns on existing config

**Checkpoint**: `otel-agent init` creates config, `otel-agent init` on existing config warns

---

## Phase 5: User Story 3 — Start Proxy (P1)

**Goal**: `otel-agent proxy` starts the MITM proxy with config-driven key rotation.

**Independent Test**: `otel-agent proxy` starts on port 8080 and prints provider summary.

### Implementation

- [ ] T016 [US3] Finalize `src/otel_agent/commands/proxy.py` with `handle_proxy(args)` function wrapping the existing `run_proxy` logic
- [ ] T017 [US3] Register `proxy` subcommand in `src/otel_agent/cli.py` with `-p`, `-u`, `-d`, `-c` flags
- [ ] T018 [P] [US3] Add test for proxy command parsing in `tests/test_cli.py`: verify default port, custom port, upstream override

**Checkpoint**: `otel-agent proxy` starts proxy, Ctrl+C shuts down gracefully

---

## Phase 6: User Story 4 — View Logged Requests (P2)

**Goal**: `otel-agent view` displays logged requests with filtering.

**Independent Test**: `otel-agent view` shows recent requests or "No requests logged yet."

### Implementation

- [ ] T019 [US4] Create `src/otel_agent/commands/view.py` with `handle_view(args)` function wrapping existing viewer logic
- [ ] T020 [US4] Register `view` subcommand in `src/otel_agent/cli.py` with `-f`, `-n`, `-d` flags
- [ ] T021 [P] [US4] Add test for view command parsing in `tests/test_cli.py`: verify defaults, filter, limit

**Checkpoint**: `otel-agent view` displays requests, `--filter` works

---

## Phase 7: User Story 5 — Manage Config (P2)

**Goal**: `otel-agent config path|show|edit` lets users manage config without remembering the file path.

**Independent Test**: `otel-agent config path` prints `~/.otel-agent/config.yaml`.

### Implementation

- [ ] T022 [US5] Create `src/otel_agent/commands/config_cmd.py` with `handle_config(args)` function supporting `path`, `show`, `edit` sub-subcommands. `show` masks API keys. `edit` opens `$EDITOR`.
- [ ] T023 [US5] Register `config` subcommand in `src/otel_agent/cli.py` with subparsers for `path`, `show`, `edit`
- [ ] T024 [P] [US5] Add tests for config subcommand in `tests/test_cli.py`: test `path` output, test `show` masks keys, test unknown subcommand error

**Checkpoint**: `otel-agent config path` prints path, `otel-agent config show` masks keys

---

## Phase 8: Doctor Command

**Purpose**: Health check for installation diagnostics

- [ ] T025 Create `src/otel_agent/commands/doctor.py` with `handle_doctor(args)` function that checks Python version >= 3.10, mitmproxy importable, config valid YAML, and port availability
- [ ] T026 Register `doctor` subcommand in `src/otel_agent/cli.py`
- [ ] T027 [P] Add test for doctor command in `tests/test_cli.py`: verify all checks reported

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup and documentation

- [ ] T028 Update `README.md` with new `otel-agent` command names (replace all `otel-proxy` references)
- [ ] T029 Update `pyproject.toml` description, classifiers, and homepage URL for PyPI readiness
- [ ] T030 Run full test suite `uv run pytest tests/ -v -m "not integration"` — all pass
- [ ] T031 Run quickstart validation from `specs/001-global-cli-tool/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 Install (Phase 3)**: Depends on Foundational
- **US2 Init (Phase 4)**: Depends on Foundational
- **US3 Proxy (Phase 5)**: Depends on Foundational
- **US4 View (Phase 6)**: Depends on Foundational
- **US5 Config (Phase 7)**: Depends on Foundational
- **Doctor (Phase 8)**: Depends on Foundational
- **Polish (Phase 9)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — no dependencies on other stories
- **US2 (P1)**: Can start after Foundational — no dependencies on other stories
- **US3 (P1)**: Can start after Foundational — no dependencies on other stories
- **US4 (P2)**: Can start after Foundational — no dependencies on other stories
- **US5 (P2)**: Can start after Foundational — no dependencies on other stories

### Parallel Opportunities

- T011 and T012 can run in parallel with T013-T015 (different files)
- T013-T015, T016-T018, T019-T021, T022-T024, T025-T027 can all run in parallel after Phase 2
- All test tasks [P] can run in parallel within their story phase

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 (Install)
4. **STOP and VALIDATE**: `otel-agent --version` works after install
5. Continue with remaining stories

### Incremental Delivery

1. Setup + Foundational → CLI works with all subcommands registered
2. Add US1 → Install verified → `uvx otel-agent --version` works
3. Add US2 → `otel-agent init` works
4. Add US3 → `otel-agent proxy` works (core value)
5. Add US4 → `otel-agent view` works
6. Add US5 → `otel-agent config` works
7. Add Doctor → `otel-agent doctor` works
8. Polish → README updated, tests green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently

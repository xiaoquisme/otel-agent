# Tasks: Background Proxy Management

**Input**: Design documents from `/specs/003-background-proxy/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/proxy-commands.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, etc.)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No new dependencies needed. Create runtime directory support.

- [ ] T001 Verify current test suite passes: `uv run pytest tests/ -v -m "not integration"`
- [ ] T002 Add `ensure_agent_dir()` helper to `src/otel_agent/process.py` that creates `~/.otel-agent/` if it doesn't exist and returns the Path

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: PID file management and process detection. All subcommands depend on this.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T003 Add `PID_FILE` constant (`~/.otel-agent/proxy.pid`) and `LOG_FILE` constant (`~/.otel-agent/proxy.log`) to `src/otel_agent/process.py`
- [ ] T004 Add `write_pid(pid: int) -> None` function that writes PID to the PID file in `src/otel_agent/process.py`
- [ ] T005 Add `read_pid() -> int | None` function that reads PID from file, returns None if file doesn't exist or contains invalid content in `src/otel_agent/process.py`
- [ ] T006 Add `is_running(pid: int) -> bool` function that checks if process is alive using `os.kill(pid, 0)` in `src/otel_agent/process.py`
- [ ] T007 Add `get_proxy_status() -> dict | None` function that reads PID, checks if running, returns `{"pid": int, "port": int}` or None in `src/otel_agent/process.py`
- [ ] T008 Add `cleanup_pid() -> None` function that deletes the PID file in `src/otel_agent/process.py`
- [ ] T009 [P] Add tests for all process.py functions: write/read/cleanup PID, is_running, stale PID detection in `tests/test_process.py`
- [ ] T010 Run `uv run pytest tests/test_process.py -v` — all pass

**Checkpoint**: PID file management works, stale detection works ✅

---

## Phase 3: User Story 1 — Start Proxy in Background (P1) 🎯 MVP

**Goal**: `otel-agent proxy` starts the proxy as a background process, writes PID file, writes logs, returns terminal control.

**Independent Test**: Run `otel-agent proxy`. Verify PID file exists, process is running, terminal returns.

### Implementation

- [ ] T011 [US1] Create `start_background(args) -> int` function in `src/otel_agent/commands/proxy.py` that spawns the proxy as a detached subprocess using `subprocess.Popen` with `start_new_session=True`, stdout/stderr redirected to log file, returns PID
- [ ] T012 [US1] Create `handle_proxy_start(args)` function in `src/otel_agent/commands/proxy.py` that checks if already running (print error), starts background, writes PID, prints status
- [ ] T013 [US1] Add `--foreground` flag to proxy subcommand in `src/otel_agent/cli.py` that runs the proxy in the current process (blocking, existing behavior)
- [ ] T014 [US1] Register `start` as default proxy subcommand in `src/otel_agent/cli.py` — when `otel-agent proxy` is called with no subcommand, default to `start`
- [ ] T015 [P] [US1] Add test for background start: verify PID file created, process is running, terminal returns in `tests/test_cli.py`

**Checkpoint**: `otel-agent proxy` starts in background, PID file exists, terminal available ✅

---

## Phase 4: User Story 2 — Stop Proxy (P1)

**Goal**: `otel-agent proxy stop` sends SIGTERM and waits for graceful shutdown.

**Independent Test**: Start proxy, run `otel-agent proxy stop`, verify process is gone and PID file deleted.

### Implementation

- [ ] T016 [US2] Create `handle_proxy_stop(args)` function in `src/otel_agent/commands/proxy.py` that reads PID, sends SIGTERM, waits up to 5s for process to exit, cleans up PID file
- [ ] T017 [US2] Register `stop` subcommand in `src/otel_agent/cli.py` under proxy command group
- [ ] T018 [US2] Add SIGTERM handler in `_run_proxy()` in `src/otel_agent/commands/proxy.py` that calls `master.shutdown()` and `logger.close()` for graceful shutdown
- [ ] T019 [P] [US2] Add test for stop: start background, stop, verify PID file deleted and process gone in `tests/test_cli.py`

**Checkpoint**: `otel-agent proxy stop` works, graceful shutdown ✅

---

## Phase 5: User Story 3 — Restart Proxy (P1)

**Goal**: `otel-agent proxy restart` stops and starts in one command.

**Independent Test**: Start proxy, run restart, verify new PID and process running.

### Implementation

- [ ] T020 [US3] Create `handle_proxy_restart(args)` function in `src/otel_agent/commands/proxy.py` that calls stop (if running) then start in `src/otel_agent/commands/proxy.py`
- [ ] T021 [US3] Register `restart` subcommand in `src/otel_agent/cli.py` under proxy command group
- [ ] T022 [P] [US3] Add test for restart: start, restart, verify new PID in `tests/test_cli.py`

**Checkpoint**: `otel-agent proxy restart` works ✅

---

## Phase 6: User Story 4 — Check Proxy Status (P2)

**Goal**: `otel-agent proxy status` shows running state, PID, and port.

**Independent Test**: Start proxy, run status, verify output shows PID and port.

### Implementation

- [ ] T023 [US4] Create `handle_proxy_status(args)` function in `src/otel_agent/commands/proxy.py` that calls `get_proxy_status()` and prints formatted output
- [ ] T024 [US4] Register `status` subcommand in `src/otel_agent/cli.py` under proxy command group
- [ ] T025 [P] [US4] Add test for status: running and not-running cases in `tests/test_cli.py`

**Checkpoint**: `otel-agent proxy status` works ✅

---

## Phase 7: User Story 5 — View Proxy Logs (P2)

**Goal**: `otel-agent proxy logs` shows recent output, `--follow` streams.

**Independent Test**: Start proxy, send request, run `otel-agent proxy logs`, verify output.

### Implementation

- [ ] T026 [US5] Create `handle_proxy_logs(args)` function in `src/otel_agent/commands/proxy.py` that reads last N lines from log file, supports `--follow` (tail -f behavior)
- [ ] T027 [US5] Register `logs` subcommand in `src/otel_agent/cli.py` under proxy command group with `--follow` and `--lines` flags
- [ ] T028 [P] [US5] Add test for logs: write to log file, read back last N lines in `tests/test_cli.py`

**Checkpoint**: `otel-agent proxy logs` and `--follow` work ✅

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [ ] T029 Update `README.md` with background proxy documentation: start/stop/restart/status/logs commands, --foreground flag
- [ ] T030 Run full test suite `uv run pytest tests/ -v -m "not integration"` — all pass
- [ ] T031 Run quickstart validation from `specs/003-background-proxy/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 Start (Phase 3)**: Depends on Foundational
- **US2 Stop (Phase 4)**: Depends on US1 (need running proxy to stop)
- **US3 Restart (Phase 5)**: Depends on US1 + US2 (stop + start)
- **US4 Status (Phase 6)**: Depends on Foundational only
- **US5 Logs (Phase 7)**: Depends on US1 (need running proxy with logs)
- **Polish (Phase 8)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational
- **US2 (P1)**: Depends on US1
- **US3 (P1)**: Depends on US1 + US2
- **US4 (P2)**: Can start after Foundational (independent of US1-3)
- **US5 (P2)**: Depends on US1

### Parallel Opportunities

- T003-T008 are sequential (same file: process.py)
- T009 can run after T008
- T011-T014 are sequential (same files: proxy.py, cli.py)
- T016-T018 are sequential (same files)
- T023-T024, T026-T027 can run in parallel after their dependencies

---

## Implementation Strategy

### MVP First (User Stories 1+2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (process.py)
3. Complete Phase 3: US1 — Background start
4. Complete Phase 4: US2 — Stop command
5. **STOP and VALIDATE**: `otel-agent proxy` + `otel-agent proxy stop` works
6. Continue with remaining stories

### Incremental Delivery

1. Setup + Foundational → PID management works
2. Add US1 → Background start works (core value!)
3. Add US2 → Stop works
4. Add US3 → Restart works
5. Add US4 → Status works
6. Add US5 → Logs works
7. Polish → README updated, tests green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently

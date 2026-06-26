# Feature Specification: Background Proxy Management

**Feature Branch**: `003-background-proxy`

**Created**: 2026-06-26

**Status**: Draft

**Input**: Start the otel-agent proxy command should run it on background, and can restart or stop it using cli command.

## User Scenarios & Testing

### User Story 1 - Start Proxy in Background (Priority: P1)

A user starts the proxy and it runs in the background, returning control of the terminal immediately.

**Why this priority**: This is the core behavior change. Currently the proxy blocks the terminal.

**Independent Test**: Run `otel-agent proxy`. Verify it starts, prints a PID, and returns terminal control.

**Acceptance Scenarios**:

1. **Given** no proxy is running, **When** the user runs `otel-agent proxy`, **Then** the proxy starts in the background and prints the PID and port.
2. **Given** the proxy is running in the background, **When** the user runs other commands, **Then** the terminal is available immediately.
3. **Given** the proxy is running, **When** the user runs `otel-agent proxy` again, **Then** the tool warns that a proxy is already running and does NOT start a second instance.

---

### User Story 2 - Stop Proxy (Priority: P1)

A user stops the running proxy with a single command.

**Why this priority**: Users must be able to stop the background process without finding the PID manually.

**Independent Test**: Start proxy, run `otel-agent proxy stop`, verify process is gone.

**Acceptance Scenarios**:

1. **Given** the proxy is running, **When** the user runs `otel-agent proxy stop`, **Then** the proxy shuts down gracefully and prints "Proxy stopped."
2. **Given** no proxy is running, **When** the user runs `otel-agent proxy stop`, **Then** the tool prints "No proxy is running."

---

### User Story 3 - Restart Proxy (Priority: P1)

A user restarts the proxy (stop + start) with a single command.

**Why this priority**: Restart is needed when config changes or the proxy gets into a bad state.

**Independent Test**: Start proxy, edit config, run `otel-agent proxy restart`, verify new config is active.

**Acceptance Scenarios**:

1. **Given** the proxy is running, **When** the user runs `otel-agent proxy restart`, **Then** the proxy stops and starts again with the current config.
2. **Given** no proxy is running, **When** the user runs `otel-agent proxy restart`, **Then** the proxy starts fresh (equivalent to `otel-agent proxy`).

---

### User Story 4 - Check Proxy Status (Priority: P2)

A user checks whether the proxy is running and which port it's on.

**Why this priority**: Users need to know if the proxy is alive before sending requests.

**Independent Test**: Start proxy, run `otel-agent proxy status`, verify it shows running status and port.

**Acceptance Scenarios**:

1. **Given** the proxy is running, **When** the user runs `otel-agent proxy status`, **Then** the tool prints "Proxy running on :8080 (PID 12345)".
2. **Given** no proxy is running, **When** the user runs `otel-agent proxy status`, **Then** the tool prints "Proxy is not running."

---

### User Story 5 - View Proxy Logs (Priority: P2)

A user views recent proxy log output (stdout/stderr from the background process).

**Why this priority**: Debugging proxy issues requires seeing its output without keeping a terminal open.

**Independent Test**: Start proxy, send a request, run `otel-agent proxy logs`, verify output shows request logs.

**Acceptance Scenarios**:

1. **Given** the proxy is running, **When** the user runs `otel-agent proxy logs`, **Then** the most recent log lines are displayed.
2. **Given** the proxy is running, **When** the user runs `otel-agent proxy logs --follow`, **Then** the output streams in real-time (like `tail -f`).
3. **Given** no proxy is running, **When** the user runs `otel-agent proxy logs`, **Then** the tool prints "No proxy is running."

---

### Edge Cases

- What happens if the PID file exists but the process is dead? The tool MUST detect stale PID, clean up, and report "Proxy is not running."
- What happens if the proxy crashes? The PID file MUST be cleaned up. `otel-agent proxy status` MUST report "Proxy is not running."
- What happens if the user runs `otel-agent proxy stop` twice? The second run MUST print "No proxy is running" (not an error).
- What happens if the port is already in use by another process? The tool MUST print "Port 8080 is in use by PID 12345. Try: otel-agent proxy -p 9090" and exit.

## Requirements

### Functional Requirements

- **FR-001**: `otel-agent proxy` MUST start the proxy as a background process and return terminal control immediately.
- **FR-002**: The background proxy MUST write its PID to `~/.otel-agent/proxy.pid`.
- **FR-003**: The background proxy MUST write stdout/stderr to `~/.otel-agent/proxy.log`.
- **FR-004**: `otel-agent proxy stop` MUST send SIGTERM to the process listed in the PID file and wait for graceful shutdown.
- **FR-005**: `otel-agent proxy restart` MUST stop the running proxy (if any) and start a new one.
- **FR-006**: `otel-agent proxy status` MUST report whether the proxy is running, the port, and the PID.
- **FR-007**: `otel-agent proxy logs` MUST display the last 50 lines of `~/.otel-agent/proxy.log`.
- **FR-008**: `otel-agent proxy logs --follow` MUST stream new log lines in real-time.
- **FR-009**: Starting a second proxy MUST be prevented with a clear message.
- **FR-010**: Stale PID files (process not running) MUST be detected and cleaned up automatically.
- **FR-011**: The proxy MUST handle SIGTERM for graceful shutdown (close SQLite, release port).
- **FR-012**: The `--port`, `--upstream`, `--db`, and `--config` flags MUST continue to work with `otel-agent proxy`.

### Key Entities

- **PID File**: `~/.otel-agent/proxy.pid` — contains the PID of the running proxy process.
- **Log File**: `~/.otel-agent/proxy.log` — stdout/stderr output from the background proxy.
- **Process**: The background proxy process, tracked by PID file.

## Success Criteria

### Measurable Outcomes

- **SC-001**: `otel-agent proxy` returns terminal control in under 1 second.
- **SC-002**: `otel-agent proxy stop` stops the proxy within 5 seconds.
- **SC-003**: `otel-agent proxy restart` completes in under 10 seconds.
- **SC-004**: `otel-agent proxy status` responds in under 1 second.
- **SC-005**: A crashed proxy is detected as "not running" by status check within 1 second.

## Assumptions

- The proxy runs as a single instance per user (one PID file).
- The PID file and log file are stored in `~/.otel-agent/` (same directory as config).
- The user has permission to send signals to their own processes.
- The proxy runs on the local machine (not in a container or remote server).
- Background mode is the default. Foreground mode is available via `otel-agent proxy --foreground` for debugging.

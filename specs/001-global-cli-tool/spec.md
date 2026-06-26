# Feature Specification: Global CLI Tool

**Feature Branch**: `001-global-cli-tool`

**Created**: 2026-06-26

**Status**: Draft

**Input**: Make otel-agent installable as a global CLI tool via `uvx` or `uv tool install`, with subcommands like `init`, `config`, `proxy`, `view` so other users can easily install and use it.

## User Scenarios & Testing

### User Story 1 - One-Command Install (Priority: P1)

A developer hears about otel-agent and wants to try it. They run a single install command and immediately have the `otel-agent` CLI available in their terminal.

**Why this priority**: If installation is hard, nobody uses the tool. This is the first impression.

**Independent Test**: Run `uvx otel-agent --version` on a clean machine. Verify the command exists and prints a version number.

**Acceptance Scenarios**:

1. **Given** the user has `uv` installed, **When** they run `uvx otel-agent --version`, **Then** the tool installs temporarily and prints the version.
2. **Given** the user has `uv` installed, **When** they run `uv tool install otel-agent`, **Then** the tool is installed globally and `otel-agent` is available on PATH.
3. **Given** the user has `pip` installed, **When** they run `pip install otel-agent`, **Then** the tool installs and `otel-agent` is available on PATH.
4. **Given** the tool is installed, **When** they run `otel-agent --help`, **Then** all available subcommands are listed with descriptions.

---

### User Story 2 - First-Time Setup (Priority: P1)

A new user wants to configure the proxy with their API keys. They run `otel-agent init` and get a working config file with guidance.

**Why this priority**: Without config, the proxy cannot inject API keys. Setup must be effortless.

**Independent Test**: Run `otel-agent init` on a fresh install. Verify `~/.otel-agent/config.yaml` is created with a valid template.

**Acceptance Scenarios**:

1. **Given** no config exists, **When** the user runs `otel-agent init`, **Then** `~/.otel-agent/config.yaml` is created with template placeholders and comments explaining each field.
2. **Given** a config already exists, **When** the user runs `otel-agent init`, **Then** the tool warns that config exists and does NOT overwrite it.
3. **Given** the config is created, **When** the user opens it, **Then** they see example provider entries with `YOUR_API_KEY` placeholders they can replace.

---

### User Story 3 - Start Proxy (Priority: P1)

A configured user wants to start the proxy. They run `otel-agent proxy` and it starts listening on a sensible default port.

**Why this priority**: This is the core value proposition — the proxy itself.

**Independent Test**: Run `otel-agent proxy` with a valid config. Verify it prints the startup banner and listens on port 8080.

**Acceptance Scenarios**:

1. **Given** a valid config exists, **When** the user runs `otel-agent proxy`, **Then** the proxy starts on port 8080 and prints a banner showing loaded providers and active key counts.
2. **Given** the proxy is running, **When** the user presses Ctrl+C, **Then** the proxy shuts down gracefully.
3. **Given** the user wants a custom port, **When** they run `otel-agent proxy -p 9090`, **Then** the proxy listens on port 9090.

---

### User Story 4 - View Logged Requests (Priority: P2)

After running some requests through the proxy, the user wants to see what was logged.

**Why this priority**: Visibility into logged requests is the second core value — debugging and monitoring.

**Independent Test**: Run `otel-agent view` after sending requests through the proxy. Verify output shows request details.

**Acceptance Scenarios**:

1. **Given** requests have been logged, **When** the user runs `otel-agent view`, **Then** the most recent 20 requests are displayed with method, URL, status, and latency.
2. **Given** the user wants to filter, **When** they run `otel-agent view --filter openai`, **Then** only requests matching "openai" are shown.
3. **Given** no requests have been logged, **When** the user runs `otel-agent view`, **Then** a message says "No requests logged yet."

---

### User Story 5 - Manage Config (Priority: P2)

A user wants to check or edit their config without remembering the file path.

**Why this priority**: Users should not need to remember `~/.otel-agent/config.yaml`.

**Independent Test**: Run `otel-agent config path` and `otel-agent config show`. Verify correct output.

**Acceptance Scenarios**:

1. **Given** the tool is installed, **When** the user runs `otel-agent config path`, **Then** the config file path is printed.
2. **Given** a config exists, **When** the user runs `otel-agent config show`, **Then** the config contents are displayed (with API keys masked).
3. **Given** the user wants to edit config, **When** they run `otel-agent config edit`, **Then** the config opens in their `$EDITOR`.

---

### Edge Cases

- What happens if `uv` is not installed? The tool MUST print a clear message: "Install uv first: https://docs.astral.sh/uv/"
- What happens if the config file has invalid YAML? The tool MUST print the YAML parse error with line number and exit.
- What happens if a provider has no active keys? The proxy MUST print a warning at startup but still start (other providers may have keys).
- What happens if port is already in use? The tool MUST print "Port 8080 is already in use. Try: otel-agent proxy -p 9090" and exit.

## Requirements

### Functional Requirements

- **FR-001**: The tool MUST be installable via `uvx otel-agent` (ephemeral run) without prior setup.
- **FR-002**: The tool MUST be installable via `uv tool install otel-agent` (persistent global install).
- **FR-003**: The tool MUST be installable via `pip install otel-agent` as a fallback.
- **FR-004**: A single `otel-agent` command MUST expose all subcommands: `init`, `proxy`, `view`, `config`.
- **FR-005**: The `init` subcommand MUST create `~/.otel-agent/config.yaml` with a documented template.
- **FR-006**: The `proxy` subcommand MUST start the MITM proxy with config-driven key rotation.
- **FR-007**: The `view` subcommand MUST display logged requests with filtering and limit options.
- **FR-008**: The `config` subcommand MUST support `path`, `show`, and `edit` actions.
- **FR-009**: The tool MUST print a version with `--version`.
- **FR-010**: Every subcommand MUST have `--help` with usage examples.
- **FR-011**: The published package name on PyPI MUST be `otel-agent`.
- **FR-012**: The tool MUST work on Linux, macOS, and WSL.

### Key Entities

- **Config**: The YAML configuration file at `~/.otel-agent/config.yaml` containing providers, keys, and active flags.
- **Provider**: A named upstream LLM API endpoint (e.g., `openai`, `anthropic`) with one or more API keys.
- **Request Log**: A recorded request/response pair stored in SQLite with full payload, headers, and latency.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A new user can go from "never heard of it" to "proxy running" in under 2 minutes.
- **SC-002**: Installation completes in under 10 seconds on a standard internet connection.
- **SC-003**: Running `otel-agent --help` shows all subcommands with one-line descriptions.
- **SC-004**: Running `otel-agent init` creates a valid config that works without manual fixes.
- **SC-005**: The tool works identically on macOS, Linux, and WSL without platform-specific instructions.

## Assumptions

- Users have Python 3.10+ installed (required by mitmproxy dependency).
- Users have `uv` installed (primary install method). `pip` is the fallback.
- Users are familiar with LLM API providers and know their API keys.
- The tool will be published to PyPI under the name `otel-agent`.
- The config file format (`~/.otel-agent/config.yaml`) remains backward-compatible.

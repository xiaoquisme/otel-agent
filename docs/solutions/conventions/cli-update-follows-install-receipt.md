---
title: "otel-agent update follows the install receipt"
date: "2026-10-19"
category: "conventions"
module: "cli"
problem_type: "convention"
component: "tooling"
severity: "medium"
applies_when:
  - "Changing `otel-agent update`"
  - "Bumping or not bumping the package version across git commits"
tags:
  - "cli"
  - "uv"
  - "update"
---

# otel-agent update follows the install receipt

## Context

`otel-agent update` upgrades a local install of the CLI. The documented install is `uv tool install git+https://github.com/xiaoquisme/otel-agent.git`. uv records that request in `uv-receipt.toml` next to the tool environment (`sys.prefix` for a `uv tool` install).

## Guidance

- Git installs are reinstalled with `uv tool install --upgrade --reinstall <git URL>`. `uv tool upgrade` keeps the receipt and can print "Nothing to upgrade" when the package version did not change. This package is not bumped on every commit.
- A resolved commit pin in the receipt is dropped so the reinstall follows the default branch. A branch or tag name is kept (`git+URL@name`).
- Editable checkouts, local directories, and local wheels are not replaced. Print the reinstall command instead.
- pip / `uv pip` git installs are force-reinstalled from the same git URL. Version equality is not treated as "already up to date".
- The published image has no uv receipt and is not a git install. Inside a container, that case prints `docker pull ghcr.io/xiaoquisme/otel-agent:latest` and exits non-zero. A uv tool receipt is still upgraded when `/.dockerenv` is present.
- When the channel is unknown outside a container, print the uv, pip, and docker commands and exit non-zero.
- After a successful upgrade, tell the user to run `otel-agent proxy restart` if the gateway is already running. The old process keeps the previous code.

## Why This Matters

Running `uv tool upgrade otel-agent` looks successful and leaves the previous git commit in place. Replacing an editable checkout or a container image with a git reinstall throws away the install the user actually has.

## When to Apply

Any change to how the CLI upgrades itself, or any new install channel that should show up in `otel-agent update`.

## Examples

Receipt at `<tool-env>/uv-receipt.toml`:

```toml
[tool]
requirements = [{ name = "otel-agent", git = "https://github.com/xiaoquisme/otel-agent.git" }]
```

Command that advances it:

```bash
uv tool install --upgrade --reinstall git+https://github.com/xiaoquisme/otel-agent.git
```

## Related Issues

- `src/otel_agent/commands/update.py` — detection and the commands it runs
- `README.md` — Commands section
- `AGENTS.md` — after a tool reinstall, restart the proxy so the new code is the one listening

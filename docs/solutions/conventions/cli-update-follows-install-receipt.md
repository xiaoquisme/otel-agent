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

- Probe before install. A git install reads the installed commit from `direct_url.json` (`commit_id`, or a commit SHA on the receipt when that is all that was recorded) and compares it to `git ls-remote` for the same ref the installer would follow. No ref means `HEAD` (default branch). A kept branch or tag name is `refs/heads/<name>`, then a peeled tag. Equal commits exit 0 with no installer. A different remote tip runs `uv tool install --upgrade --reinstall` or the pip equivalent.
- Do not treat `__version__` equality as "up to date" for git. This package is not bumped on every commit. `uv tool upgrade` can also report nothing to do for that reason, which is why the git path reinstalls from the URL only after `ls-remote` says the tip moved.
- A resolved commit pin in the receipt is dropped so the probe and the reinstall follow the default branch. A branch or tag name is kept (`git+URL@name`).
- Registry uv-tool installs run `uv pip install --dry-run --upgrade --no-deps <requirement>` against the receipt's version constraint. `uv tool upgrade` runs only when that dry run shows a different `otel-agent` version. `Would make no changes` exits 0.
- If the probe cannot tell (missing commit id, `git` or `uv` missing, `ls-remote` or dry-run error, ambiguous output), print the error and the reinstall command, and do not install.
- Editable checkouts, local directories, local wheels, direct URLs, uvx, and unknown channels stay guidance-only.
- The published image has no uv receipt and is not a git install. Inside a container, that case prints `docker pull ghcr.io/xiaoquisme/otel-agent:latest` and exits non-zero. A uv tool receipt is still eligible for the probe when `/.dockerenv` is present.
- When the channel is unknown outside a container, print the uv, pip, and docker commands and exit non-zero.
- After a successful upgrade, tell the user to run `otel-agent proxy restart` if the gateway is already running. The old process keeps the previous code. An already-current install does not ask for a restart.

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

Probe, then the command that advances it when `HEAD` differs from the installed commit:

```bash
git ls-remote https://github.com/xiaoquisme/otel-agent.git HEAD
uv tool install --upgrade --reinstall git+https://github.com/xiaoquisme/otel-agent.git
```

## Related Issues

- `src/otel_agent/commands/update.py` — detection and the commands it runs
- `README.md` — Commands section
- `AGENTS.md` — after a tool reinstall, restart the proxy so the new code is the one listening

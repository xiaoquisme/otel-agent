<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/020-dashboard-usage-metrics/plan.md
<!-- SPECKIT END -->

## Documented Solutions

`docs/solutions/` — documented solutions to past problems (architecture patterns, bugs, best practices), organized by category with YAML frontmatter (`module`, `tags`, `problem_type`). Relevant when implementing or debugging in documented areas.

`CONCEPTS.md` — shared domain vocabulary (Thompson Sampling, Circuit Breaker, Tier, etc.) — relevant when orienting to the codebase or discussing domain concepts.

## Dashboard CLI landmine

`:45638` is a `uv tool install` proxy, not the repo checkout. After a UI change, commit `src/otel_agent/dashboard/frontend_dist/`, then `uv tool install --force .`, then `otel-agent proxy restart`. Install without restart still serves the old process. Do not treat a leftover `frontend/dist` as what the CLI ships — hatch keeps the committed `frontend_dist` when that tree already has `index.html`.

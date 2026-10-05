<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/020-dashboard-usage-metrics/plan.md
<!-- SPECKIT END -->

## Documented Solutions

`docs/solutions/` — documented solutions to past problems (architecture patterns, bugs, best practices), organized by category with YAML frontmatter (`module`, `tags`, `problem_type`). Relevant when implementing or debugging in documented areas.

`CONCEPTS.md` — shared domain vocabulary (Sidecar Auth Vault, SuperGrok Grant, etc.) — relevant when orienting to the codebase or discussing domain concepts.

## Dev Workflow Harness（操控循环）

每个开发任务（feature / bugfix）按操控循环执行；规模大、多步骤的任务先在 `docs/plans/` 出计划（外层 PDCA），拆成可验收的步骤，逐项通过再进下一步。

1. **【前馈】开工条件**：读本次 `docs/plans/*-plan.md` / `specs/<NNN>/plan.md`、`CONCEPTS.md`、`docs/solutions/` 相关分类；上下文不足时列出缺失项并停下等用户，不得臆造 API 或行为
2. **【前馈】实现约束**：遵循上方 Documented Solutions 与 Dashboard CLI landmine；领域词汇以 `CONCEPTS.md` 为准
3. **【行动】** 按计划实现，测试随手补
4. **【反馈·推断型】自检**：改动与既有架构模式一致、没有破坏 solutions 里的约定、错误处理覆盖已知 runtime-errors
5. **【反馈·计算型】** `bash harness/checks.sh` 全绿才算完成（可复现环境见 `harness/ENV.md`）
6. **【调整】** 失败则修复并重跑 3-5，重复直到全绿；连续失败说明计划有问题，回到步骤 1 修订
7. **【状态】** 新解法写入 `docs/solutions/<分类>/`（YAML frontmatter：`module`/`tags`/`problem_type`），需要时更新 `CONCEPTS.md` 词汇

## Dashboard CLI landmine

`:45638` is a `uv tool install` proxy, not the repo checkout. After a UI change, commit `src/otel_agent/dashboard/frontend_dist/`, then `uv tool install --force .`, then `otel-agent proxy restart`. Install without restart still serves the old process. Do not treat a leftover `frontend/dist` as what the CLI ships — hatch keeps the committed `frontend_dist` when that tree already has `index.html`.

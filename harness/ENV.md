# 环境（Environment 子系统）

反馈信号只有在一致的环境下才可信：测试要跑在固定依赖版本上，检查规则每次相同。

## 后端（Python）

- Python >= 3.10；依赖一律用 **uv** 管理，`uv.lock` 是唯一事实来源，不要手改依赖
- 安装：`uv sync`（含 dev 依赖：pytest、build、twine）
- 测试入口统一走 `harness/checks.sh`，等价命令：
  - 单元测试：`uv run pytest tests/ -q -m "not integration"`（约 490 用例）
  - integration：`uv run pytest tests/ -q -m "integration"`（需外网/真实凭证，本地通常跳过）

## 前端（dashboard，`frontend/`）

- Node.js + npm（构建链：Vite + TypeScript，lint 用 oxlint）
- 安装：`cd frontend && npm ci`
- 构建：`npm run build`（产物须同步到 `src/otel_agent/dashboard/frontend_dist/`，见 AGENTS.md landmine）

## 容器 / 部署

- `Dockerfile` + `docker-compose.yml`；镜像由 `.github/workflows/docker-image.yml` 多架构构建并 smoke test `/health`
- 运行时状态在 `~/.otel-agent/`（`config.yaml`、`telemetry.sqlite`、`auth.json`），容器内为 `/home/otel/.otel-agent`

## 版本与工具约定

| 项 | 固定方式 |
|---|---|
| Python 依赖 | `uv.lock` |
| 前端依赖 | `frontend/package-lock.json`（用 `npm ci` 安装） |
| 测试选择器 | `-m "not integration"` 为默认门禁 |

#!/usr/bin/env bash
# 计算型验收入口（工具子系统）：确定性检查交给代码，不交给 LLM。
# 全部通过退出码 0。用法：
#   bash harness/checks.sh               # 默认：单元测试 + 一致性检查
#   bash harness/checks.sh --integration # 追加 integration 测试（需外网/凭证）
set -u
cd "$(dirname "$0")/.."

fail=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; fail=1; }

# ── 1. 后端单元测试（核心反馈信号） ─────────────────────────────
if uv run pytest tests/ -q -m "not integration"; then
  ok "pytest 单元测试"
else
  bad "pytest 单元测试"
fi

# ── 2. Dashboard frontend_dist landmine ─────────────────────────
# 改了 frontend/ 就必须同步提交 src/otel_agent/dashboard/frontend_dist/
# （AGENTS.md “Dashboard CLI landmine”：hatch 优先保留已提交的 frontend_dist）
changed=$(git diff --name-only HEAD 2>/dev/null)
if echo "$changed" | grep -q '^frontend/'; then
  if echo "$changed" | grep -q '^src/otel_agent/dashboard/frontend_dist/'; then
    ok "frontend_dist 已随 frontend/ 同步更新"
  else
    bad "改动了 frontend/ 但未更新 src/otel_agent/dashboard/frontend_dist/（见 AGENTS.md landmine）"
  fi
fi

# ── 3. 前端 lint（仅当 frontend/ 有改动时） ─────────────────────
if echo "$changed" | grep -q '^frontend/'; then
  if (cd frontend && npm run lint); then
    ok "前端 lint (oxlint)"
  else
    bad "前端 lint (oxlint)"
  fi
fi

# ── 4. 可选：integration 测试 ───────────────────────────────────
if [ "${1:-}" = "--integration" ]; then
  if uv run pytest tests/ -q -m "integration"; then
    ok "pytest integration"
  else
    bad "pytest integration"
  fi
fi

exit $fail

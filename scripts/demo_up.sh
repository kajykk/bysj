#!/usr/bin/env bash
# 一键拉起全栈演示（P1）：端口冲突检测 -> compose up -> 健康检查。
# 用法：bash scripts/demo_up.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PORTS=(80 443 3001 8001 9090)
conflict=0
for p in "${PORTS[@]}"; do
  if (command -v ss >/dev/null && ss -ltn | grep -q ":$p ") || \
     (command -v netstat >/dev/null && netstat -ltn 2>/dev/null | grep -q ":$p "); then
    echo "[conflict] 端口 $p 被占用（Grafana 3001 常见为旧栈残留，见 docs/DEMO_CHECKLIST.md）"
    conflict=1
  fi
done
if [ "$conflict" -eq 1 ]; then
  echo "[abort] 请先释放冲突端口或按 DEMO_CHECKLIST 调整映射后重跑。"
  exit 1
fi

docker compose up -d --build
echo "[wait] 等待 backend healthy..."
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8001/health >/dev/null 2>&1; then
    echo "[ok] 全栈已拉起：$(curl -s http://127.0.0.1:8001/health)"
    exit 0
  fi
  sleep 10
done
echo "[fail] backend 300s 内未 healthy，请 docker compose ps / logs backend 排查。"
exit 1

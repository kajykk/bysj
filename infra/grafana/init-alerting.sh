#!/bin/sh
# H-AUDIT-01 修复: Grafana 告警投递初始化
#
# Grafana 11.5 的 alerting provisioning 不支持 ${env:XXX} 占位符,
# 且 contact-points 在卷首次初始化时才会被加载。本脚本在容器启动时
# (grafana 主进程运行前) 用环境变量渲染 provisioning 文件中的占位符,
# 将 Grafana 告警接入 backend 的 /api/v1/alerts/webhook (系统自身告警管线),
# 密钥不进 git、不出现在镜像层。
#
# 渲染目标位于独立命名卷 (grafana_provisioning_alerting), 宿主机仓库中的
# contact-points.yaml 以只读方式挂载为模板, 永远不会被回写,
# 因此渲染后的真实密钥不会出现在 git 工作区。
#
# 注意: alerting provisioning 仅在 grafana 数据卷首次初始化时生效。
# 已有旧数据卷 (含旧 contact point) 需执行:
#   docker compose rm -sf grafana \
#     && docker volume rm <project>_grafana_data <project>_grafana_provisioning_alerting
# 或在 Grafana UI 中删除旧 contact point 后重启。
#
# 占位符:
#   __WEBHOOK_URL__    -> ALERT_WEBHOOK_URL  (默认 http://backend:8000/api/v1/alerts/webhook)
#   __WEBHOOK_SECRET__ -> ALERTMANAGER_WEBHOOK_SECRET (默认 dev-only-webhook-secret, 生产必须在 .env 配置)
#   __SRE_EMAIL__      -> GRAFANA_SRE_EMAIL (默认 sre-alerts@example.invalid, RFC2606 保留域, 无外部投递)

set -eu

SRC_DIR="/etc/grafana/provisioning-src/alerting"
DST_DIR="/etc/grafana/provisioning/alerting"
TARGET="${DST_DIR}/contact-points.yaml"

if [ ! -f "${SRC_DIR}/contact-points.yaml" ]; then
  echo "[init-alerting] ${SRC_DIR}/contact-points.yaml not found, skip rendering" >&2
  exec /run.sh "$@"
fi

mkdir -p "$DST_DIR"
if [ ! -f "$TARGET" ]; then
  cp "${SRC_DIR}/contact-points.yaml" "$TARGET"
fi

WEBHOOK_URL="${ALERT_WEBHOOK_URL:-http://backend:8000/api/v1/alerts/webhook}"
WEBHOOK_SECRET="${ALERTMANAGER_WEBHOOK_SECRET:-dev-only-webhook-secret}"
SRE_EMAIL="${GRAFANA_SRE_EMAIL:-sre-alerts@example.invalid}"

if ! grep -q '__WEBHOOK_URL__' "$TARGET"; then
  # 已渲染过 (卷复用), 直接启动
  exec /run.sh "$@"
fi

# sed 替换侧转义: & / \ / | 均为特殊字符, secret 含这些字符时必须转义
escape_sed_repl() {
  printf '%s' "$1" | sed 's/[&\\|]/\\&/g'
}

sed -i \
  -e "s|__WEBHOOK_URL__|$(escape_sed_repl "$WEBHOOK_URL")|g" \
  -e "s|__WEBHOOK_SECRET__|$(escape_sed_repl "$WEBHOOK_SECRET")|g" \
  -e "s|__SRE_EMAIL__|$(escape_sed_repl "$SRE_EMAIL")|g" \
  "$TARGET"
chmod 600 "$TARGET"

echo "[init-alerting] rendered $TARGET (webhook_url=${WEBHOOK_URL})"

exec /run.sh "$@"

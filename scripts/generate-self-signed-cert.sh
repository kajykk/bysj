#!/usr/bin/env bash
# SEC-P1-006: 生成开发/测试环境自签名 TLS 证书
#
# 用途: docker-compose 的 frontend (nginx) 以 HTTPS 提供服务,
# 首次克隆仓库时 infra/nginx/certs 下没有证书 (该目录被 .gitignore 排除),
# 需运行本脚本生成。输出:
#   infra/nginx/certs/server.crt  (证书, SAN: localhost / 127.0.0.1 / 传入域名)
#   infra/nginx/certs/server.key  (私钥, 权限 600)
#
# 用法:
#   bash scripts/generate-self-signed-cert.sh            # 默认 localhost
#   bash scripts/generate-self-signed-cert.sh example.com
#
# 注意: 自签名证书仅用于开发/测试; 生产环境请替换为受信 CA 证书 (如 Let's Encrypt)。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${SCRIPT_DIR}/../infra/nginx/certs"
DOMAIN="${1:-localhost}"

mkdir -p "${CERT_DIR}"

# 生成自签名证书: RSA 2048, 私钥不加密 (-nodes), SAN 覆盖 localhost/127.0.0.1
openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "${CERT_DIR}/server.key" \
  -out "${CERT_DIR}/server.crt" \
  -days 825 \
  -subj "/CN=${DOMAIN}" \
  -addext "subjectAltName=DNS:${DOMAIN},DNS:localhost,IP:127.0.0.1"

chmod 600 "${CERT_DIR}/server.key"

echo "自签名证书已生成: ${CERT_DIR}/server.crt (SAN: ${DOMAIN}, localhost, 127.0.0.1)"
echo "仅用于开发/测试; 生产环境请使用受信 CA 证书 (如 Let's Encrypt)"

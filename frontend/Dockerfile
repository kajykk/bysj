# P1-INFRA-030 修复：前端容器化（多阶段构建）
# 阶段1: Node 构建静态资源
# 阶段2: Nginx 提供静态服务 + SPA 路由回退 + API 反向代理

# ── Build Stage ──
# T-P0-04: 升级至 Alpine 3.22 (修复 c-ares/libexpat/libpng/libssl3/xz-libs/zlib 等 CVE)
FROM node:20.19.5-alpine3.22 AS builder
WORKDIR /app

# T-P0-04: build context 改为项目根目录, 以支持 @common 别名 (../common)
# 先复制依赖文件，利用 Docker 层缓存
COPY frontend/package.json frontend/package-lock.json* ./
# 复制 .npmrc 配置 (中国镜像加速)
COPY frontend/.npmrc ./
# M-FE-17 修复：去掉 2>/dev/null，避免 npm ci 错误被静默吞掉
# FIX(build): --ignore-scripts 跳过 postinstall 的 `playwright install chromium`
# (170MB 下载, cdn.playwright.dev 国内不可达导致构建卡死/超时; 浏览器仅 e2e 需要,
# CI 中由 npx playwright install 显式安装)。esbuild/rollup 通过 optionalDependencies
# 分发平台预编译二进制, 不受 --ignore-scripts 影响。
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PUPPETEER_SKIP_DOWNLOAD=true
RUN npm ci --ignore-scripts --prefer-offline || npm install --ignore-scripts

# 复制前端源码与共享 common 目录 (vite @common 别名指向 ../common)
COPY frontend/ ./
COPY common/ ../common/
RUN npm run build

# ── Production Stage ──
# T-P0-04: 升级至 Alpine 3.22 (与 builder 阶段一致, 修复 OpenSSL/libexpat 等 CVE)
# 注: 1.27.4-alpine3.22 tag 不存在, 使用 alpine3.22 (latest nginx on alpine 3.22)
FROM nginx:alpine3.22 AS production

# T-P0-04: apk upgrade 升级基础镜像中所有系统包至最新补丁版本
# 修复 trivy HIGH/CRITICAL 漏洞:
#   - libcrypto3/libssl3 (OpenSSL) 3.5.4-r0 → 3.5.7-r0 (CVE-2026-31789 等 8 项)
#   - libexpat 2.7.3-r0 → 2.8.2-r0 (CVE-2026-25210/45186/56131/56407/56408)
#   - libpng 1.6.47-r0 → 1.6.55-r0 (CVE-2025-64720 等 6 项)
#   - libxml2 2.13.9-r0 → 2.13.9-r1 (CVE-2026-6732)
#   - musl/musl-utils 1.2.5-r10 → 1.2.5-r12 (CVE-2026-40200)
#   - nghttp2-libs 1.65.0-r0 → 1.68.1 (CVE-2026-27135)
#   - zlib 1.3.1-r2 → 1.3.2-r0 (CVE-2026-22184)
#   - c-ares 1.34.5-r0 → 1.34.8-r0 (CVE-2026-33630)
# nginx:alpine3.22 基础镜像发布时这些包是当时的版本, 但上游已有安全补丁, 需显式升级
RUN apk upgrade --no-cache

# RES-P2-008: ngx_brotli 模块已移除
# 原因: Alpine 3.22 仓库的 nginx-mod-http-brotli 为 nginx 1.28.x 编译 (module version 1028003),
# 但 nginx:alpine3.22 镜像中的 nginx 为 1.29.3 (需要 module version 1029003),
# 版本不匹配导致 nginx 启动失败 [emerg] module version mismatch.
# Brotli 是可选的传输压缩优化 (比 gzip 压缩率高 15-25%), 非核心功能.
# nginx 默认仍提供 gzip 压缩, 功能不受影响. 待 Alpine 仓库更新 brotli 模块至 1.29.x 后可恢复.

# 复制自定义 nginx 配置
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# SEC-P1-006 修复: 移除 USER nginx, 恢复 nginx 默认安全模型
# (master 进程以 root 启动绑定 80/443 端口, worker 进程以 nginx 用户运行)
# 原因: 443 < 1024 为特权端口, 非 root 用户无法绑定
# 安全性: 容器内 root 与宿主机 root 隔离 (Docker 命名空间), nginx master root + worker nginx 是 nginx 标准模型
# 确保 worker 进程仍以非特权 nginx 用户运行 (由 nginx.conf 默认 user 指令控制)
RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/log/nginx /etc/nginx/conf.d \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid

EXPOSE 80 443

# L-FE-14 修复：HEALTHCHECK 改为检查 nginx 代理的后端 /health 端点，
# 既验证 nginx 正常运行，又验证后端服务可达（分层架构：nginx 反代 backend:8000）
# SEC-P1-006: 80 端口现在 301 跳转到 443, 直接检查 HTTPS (自签名证书需 --no-check-certificate)
# T-P0-04 修正: nginx 已同时监听 IPv4+IPv6 (listen [::]:80/443), 解决健康检查环境
# 中 localhost 解析为 ::1 而 nginx 仅监听 IPv4 导致 wget 失败的问题
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD wget --spider -q --no-check-certificate https://localhost/health || exit 1

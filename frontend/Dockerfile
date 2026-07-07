# P1-INFRA-030 修复：前端容器化（多阶段构建）
# 阶段1: Node 构建静态资源
# 阶段2: Nginx 提供静态服务 + SPA 路由回退 + API 反向代理

# ── Build Stage ──
FROM node:20.19.2-alpine3.20 AS builder
WORKDIR /app

# 先复制依赖文件，利用 Docker 层缓存
COPY package.json package-lock.json* ./
# M-FE-17 修复：去掉 2>/dev/null，避免 npm ci 错误被静默吞掉
RUN npm ci --prefer-offline || npm install

# 复制源码并构建
COPY . .
RUN npm run build

# ── Production Stage ──
FROM nginx:1.27.4-alpine AS production

# 复制自定义 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

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
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -q --no-check-certificate --spider https://localhost/health || exit 1

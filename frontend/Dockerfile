# P1-INFRA-030 修复：前端容器化（多阶段构建）
# 阶段1: Node 构建静态资源
# 阶段2: Nginx 提供静态服务 + SPA 路由回退 + API 反向代理

# ── Build Stage ──
FROM node:20-alpine AS builder
WORKDIR /app

# 先复制依赖文件，利用 Docker 层缓存
COPY package.json package-lock.json* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install

# 复制源码并构建
COPY . .
RUN npm run build

# ── Production Stage ──
FROM nginx:1.27-alpine AS production

# 复制自定义 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 非 root 用户运行（安全基线）
RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/log/nginx /etc/nginx/conf.d \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -q --spider http://localhost:80/ || exit 1

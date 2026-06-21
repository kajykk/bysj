# v1.10 需求文档: 监控硬化、性能优化与安全加固

> **迭代名称**: v1.10-monitoring-hardening-performance-security
> **日期**: 2026-04-29
> **版本**: Round 3 Locked
> **状态**: Locked

---

## 1. 项目概述

### 1.1 背景
v1.9 迭代已完成 E2E 测试基础设施、Lighthouse CI 配置、Sentry + Web Vitals 监控体系搭建。但监控体系尚未完全硬化（Sentry 后端 SDK 未实际安装），性能优化仍停留在配置层面，安全加固尚未启动。

### 1.2 目标
将 v1.9 搭建的监控、性能、安全基础设施从"配置可用"推进到"生产就绪"。

### 1.3 目标用户
- **开发团队**: 需要完整的错误监控和性能洞察
- **运维团队**: 需要可触发的告警规则
- **最终用户**: 需要更快的页面加载和更安全的数据传输

---

## 2. 详细功能设计

### 2.1 模块 A: 监控硬化 (Monitoring Hardening)

#### 2.1.1 Sentry 后端 SDK 集成
**路径**: `backend/app/main.py`

**需求详情**:
| 元素名称 | 类型 | 验证规则 | 默认值 | 交互逻辑 | 异常处理 | 权限 |
|---|---|---|---|---|---|---|
| Sentry DSN | 环境变量 | Required, URL Format | - | 从 `.env` 读取 | 缺失则禁用 Sentry | 系统 |
| 采样率 | 配置项 | 0.0 ~ 1.0 | 1.0 (开发) / 0.1 (生产) | 按环境区分 | 无效值回退到 0.1 | 系统 |
| 性能监控 | 开关 | Boolean | true | 启用 transactions | 失败不影响主流程 | 系统 |

**逻辑流程**:
1. 应用启动时初始化 Sentry SDK
2. 捕获所有未处理异常 (包括 FastAPI RequestValidationError)
3. 记录性能 transactions (数据库查询、HTTP 请求)
4. 关联前端用户 (通过 request_id / trace_id)
5. **Graceful Degradation**: DSN 缺失时静默跳过，不影响应用启动

#### 2.1.2 告警规则配置
**路径**: `backend/app/monitoring/alerting-rules.yml`

**规则清单**:
| 规则名称 | 触发条件 | 通知渠道 | 优先级 |
|---|---|---|---|
| 错误率飙升 | 5分钟内错误率 > 5% | 日志 + Webhook | P0 |
| 慢请求告警 | P99 响应时间 > 3s | 日志 + Webhook | P1 |
| 内存使用率高 | 内存使用率 > 85% | 日志 | P1 |
| 磁盘空间不足 | 磁盘使用率 > 90% | 日志 | P2 |

**Webhook 配置**:
| 配置项 | 说明 | 默认值 |
|---|---|---|
| webhook_url | 告警通知地址 | 空 (不发送) |
| webhook_timeout | 请求超时 | 5s |
| webhook_retry | 失败重试次数 | 3 |

#### 2.1.3 监控 Dashboard
**路径**: `/admin/monitoring`

**关键指标**:
- 错误率趋势 (最近 1h/24h/7d)
- 平均响应时间
- Web Vitals 分布 (CLS, LCP, FID)
- 慢请求 Top 10

### 2.2 模块 B: 性能优化 (Performance Optimization)

#### 2.2.1 图片 WebP 格式支持
**路径**: `frontend/src/components/ImageUploader.vue`, `frontend/public/`

**需求详情**:
| 元素名称 | 类型 | 验证规则 | 默认值 | 交互逻辑 | 异常处理 |
|---|---|---|---|---|---|
| 图片格式 | 选择器 | JPG/PNG/WebP | WebP | 上传时自动转换 | 转换失败保留原格式 |
| 压缩质量 | 滑块 | 0 ~ 100 | 85 | 实时预览压缩效果 | - |
| 响应式图片 | 自动生成 | 多尺寸 srcset | - | 根据 DPR 加载 | 回退到默认尺寸 |
| WebP 降级 | 自动检测 | Accept 头 / `<picture>` | - | 不支持 WebP 时返回 JPEG | 透明通道保留 PNG |

#### 2.2.2 Service Worker 缓存策略
**路径**: `frontend/src/service-worker.ts`

**缓存策略**:
| 资源类型 | 策略 | 缓存时间 | 版本控制 |
|---|---|---|---|
| 静态资源 (JS/CSS) | Cache First | 7天 | 构建哈希 |
| API 响应 | Network First | 5分钟 | - |
| 图片 | Stale While Revalidate | 1天 | - |
| 离线页面 | Cache Only | - | - |

**Service Worker 版本管理**:
- 缓存名称包含构建版本号 (`static-v{BUILD_NUMBER}`)
- 新 SW 激活时自动清理旧版本缓存
- 提供 "更新可用" 提示，用户确认后刷新

#### 2.2.3 路由懒加载与代码分割
**路径**: `frontend/src/router/index.ts`

**优化点**:
- 所有非首屏路由启用懒加载
- 组件库按需导入 (ant-design-vue)
- 大图表库动态导入

### 2.3 模块 C: 安全加固 (Security Hardening)

#### 2.3.1 Content Security Policy (CSP)
**路径**: `backend/app/middleware/security.py`, Nginx/CDN 配置

**CSP 部署策略**:
- **Phase 1 (Report-Only)**: 先使用 `Content-Security-Policy-Report-Only` 收集违规报告
- **Phase 2 (强制执行)**: 确认无违规后切换到 `Content-Security-Policy`

**CSP 指令 (最终版)**:
```
default-src 'self';
script-src 'self' 'nonce-{random}';
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:;
connect-src 'self' https://sentry.io;
font-src 'self';
frame-ancestors 'none';
base-uri 'self';
form-action 'self';
report-uri /api/csp-report;
```

**CSP 报告端点**: `POST /api/csp-report`
- 接收浏览器 CSP 违规报告
- 记录到日志供分析
- 不阻塞用户请求

#### 2.3.2 HTTPS 强制与安全头
**路径**: `backend/app/middleware/security.py`

**安全头清单**:
| 头部名称 | 值 | 说明 |
|---|---|---|
| Strict-Transport-Security | max-age=31536000; includeSubDomains | HSTS |
| X-Content-Type-Options | nosniff | 防止 MIME 嗅探 |
| X-Frame-Options | DENY | 防止点击劫持 |
| Referrer-Policy | strict-origin-when-cross-origin | 控制 Referrer |
| Permissions-Policy | geolocation=(), microphone=() | 限制 API 权限 |

#### 2.3.3 输入验证与 XSS 防护
**路径**: 全局中间件

**措施**:
- 所有用户输入启用 HTML 转义
- 富文本使用 DOMPurify 净化
- 文件上传限制类型和大小

### 2.4 模块 D: 可访问性 (Accessibility)

#### 2.4.1 ARIA 属性完善
**路径**: 全局组件

**要求**:
- 所有交互元素有明确的 `role` 和 `aria-label`
- 表单控件关联 `label`
- 动态内容使用 `aria-live`

#### 2.4.2 键盘导航
**路径**: 全局组件

**要求**:
- 所有功能可通过键盘操作
- 焦点顺序符合逻辑
- 提供跳过导航链接 (Skip to main content)

**快捷键规范** (避免浏览器冲突):
| 快捷键 | 功能 | 冲突检查 |
|---|---|---|
| Tab / Shift+Tab | 焦点移动 | 无冲突 |
| Enter / Space | 激活按钮/链接 | 无冲突 |
| Escape | 关闭 Modal/Toast | 无冲突 |
| Alt+Shift+1 | 跳转到主内容区 | 避开 Alt+1 (Chrome 收藏夹) |
| Alt+Shift+M | 打开消息通知 | 避开常用快捷键 |

---

## 3. 非功能需求

### 3.1 性能
- Lighthouse Performance >= 80
- FCP < 1.5s, LCP < 2.5s
- 首屏 JS 体积 < 200KB (gzip)

### 3.2 安全
- OWASP Top 10 防护
- 通过 securityheaders.com A 级评分
- 无高危/严重漏洞 (npm audit / pip audit)

### 3.3 兼容性
- 支持 Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
- Service Worker 渐进增强 (不支持则静默降级)

### 3.4 可维护性
- 所有监控配置可热更新
- 安全头配置集中管理
- 文档完整记录回退策略

### 3.5 新增: 分布式追踪
- 所有请求携带 `X-Request-ID` 头
- Sentry 前后端通过 `trace_id` 关联
- 日志中统一包含 `request_id` 字段

---

## 4. 假设与约束

- **假设**: Sentry DSN 可从环境变量获取
- **假设**: 生产环境使用 HTTPS
- **约束**: Service Worker 不缓存敏感数据
- **约束**: CSP 升级需逐步进行，避免阻断现有功能

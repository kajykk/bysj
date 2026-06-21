# Architecture v1.11 - Production Readiness Hardening

> 迭代：v1.11-production-readiness-hardening  
> 日期：2026-04-29  
> 状态：Round 3 Locked (Final)  
> 基线版本：v1.10.1
>
> **Round 1 决策记录**:
> - PWA: 采用 `vite-plugin-pwa` (未安装，需新增)
> - SW: 使用 `generateSW` 策略，`src/service-worker.ts` 将废弃
> - Manifest: 需新建，通过插件自动生成
> - Lighthouse: 环境限制，配置验证替代实际运行
> - CSP Report: 新增 `POST /api/csp-report` 端点

---

## 1. 架构目标

v1.11 的架构目标是补齐 v1.10.1 暴露的生产化缺口：

1. PWA 能力从源码存在变为生产可用。
2. Lighthouse 从配置存在变为实际门禁。
3. CSP 从响应头配置变为报告闭环。
4. 测试覆盖从局部高覆盖变为核心模块稳定覆盖。
5. 性能优化从 chunk 发现变为首屏控制。
6. 可访问性从基础 ARIA 修复扩展到图表可访问性。

---

## 2. 总体架构

```text
Frontend
  ├── Vite 6
  ├── Vue 3
  ├── vite-plugin-pwa
  ├── Workbox Runtime Caching
  ├── Lighthouse CI
  ├── Lazy Route / Dynamic Import
  └── Accessible Chart Components

Backend
  ├── FastAPI
  ├── Security Headers Middleware
  ├── CSP Report API
  ├── XSS Middleware
  ├── Monitoring / Alerting
  ├── Analytics / Web Vitals API
  └── pytest + pytest-cov

Quality Gate
  ├── npm run build
  ├── npm run lint
  ├── npm audit
  ├── bandit
  ├── pytest --cov
  ├── Lighthouse
  └── PWA Offline Verification
```

---

## 3. PWA 架构

### 3.1 方案选择

采用：

```text
Vite 6 + vite-plugin-pwa + Workbox generateSW
```

**决策**: 使用 `generateSW` 策略，废弃现有 `src/service-worker.ts` 手写代码。

### 3.2 选择理由

| 选项 | 结论 | 原因 |
|---|---|---|
| vite-plugin-pwa | 采用 | 与 Vite 6 集成好，配置简单，支持虚拟模块注册 |
| workbox-cli | 暂不采用 | 需要额外脚本，维护成本更高 |
| 手写 src/service-worker.ts | **废弃** | 与构建产物脱节，缓存策略难以维护 |
| injectManifest | v1.12 可考虑 | 适合复杂离线写入场景，当前 generateSW 足够 |

### 3.3 现有代码处理

```text
src/service-worker.ts     → 废弃（不再使用）
src/utils/serviceWorker.ts → 重构（使用 virtual:pwa-register）
public/offline.html        → 保留（配置为 globPatterns 预缓存）
```

---

## 4. Workbox 缓存策略

| 资源类型 | 策略 | 说明 |
|---|---|---|
| HTML / SPA 导航 | NetworkFirst | 优先获取新版本 |
| JS/CSS/字体 | CacheFirst | 构建产物 hash，可长期缓存 |
| 图片 | StaleWhileRevalidate | 兼顾速度与更新 |
| API GET | NetworkFirst | 可短缓存 |
| API POST/PUT/DELETE | 不缓存 | 避免数据一致性问题 |
| `offline.html` | Precache | 离线兜底 |

---

## 5. PWA 注册架构

前端入口负责注册 Service Worker：

```text
main.ts
  └── registerServiceWorker()
        └── virtual:pwa-register
              ├── onNeedRefresh
              ├── onOfflineReady
              └── updateServiceWorker
```

注册逻辑要求：

1. 仅生产环境启用。
2. 支持更新提示。
3. 支持离线可用提示。
4. 不缓存敏感非 GET API。

---

## 6. CSP Report 架构

### 6.1 当前状态

v1.10 已配置：

```text
Content-Security-Policy-Report-Only: ...; report-uri /api/csp-report
```

但后端缺少完整端点。

### 6.2 v1.11 架构

新增：

```text
POST /api/csp-report
```

支持：

```text
application/csp-report
application/json
application/reports+json
```

### 6.3 处理流程

```text
Browser CSP Violation
  ↓
POST /api/csp-report
  ↓
Payload Size Check
  ↓
Schema Normalize
  ↓
Sensitive Field Sanitization
  ↓
Rate Limit / Sampling
  ↓
Application Log / Optional Sentry Breadcrumb
```

---

## 7. CSP 迁移路线

v1.11 不直接强制移除 `unsafe-inline`。

采用三阶段：

```text
阶段 1：Report-Only + /api/csp-report
阶段 2：nonce 支持 + 预发验证
阶段 3：v1.12 生产 Enforcement
```

---

## 8. 测试覆盖架构

### 8.1 原则

采用风险优先覆盖，不盲目追求低价值覆盖率。

### 8.2 覆盖优先级

| 优先级 | 模块 |
|---|---|
| P0 | core、security、health、middleware、auth |
| P1 | csp-report、analytics、upload、xss、alerting |
| P2 | services、ML canary、fusion |
| P3 | 历史低风险 CRUD |

### 8.3 覆盖率目标

| 范围 | v1.11 目标 |
|---|---:|
| backend overall | >= 40% |
| core | >= 80% |
| 新增/修改代码 | >= 80% |

---

## 9. 性能架构

### 9.1 当前问题

v1.10.1 构建显示：

| Chunk | 大小 |
|---|---:|
| charts | 813KB |
| vendor | 621KB |
| vue-core | 483KB |
| ui | 427KB |

### 9.2 优化原则

不以所有 chunk 都小于 300KB 为唯一目标，而以首屏加载和 Lighthouse 为准。

### 9.3 策略

1. 路由级懒加载（已存在）。
2. 图表页面懒加载（已存在）。
3. ECharts / charts 不进入登录页（已配置 manualChunks）。
4. vendor 拆分为（已配置）：
   - vue-core
   - router
   - state
   - ui
   - icons
   - charts
   - datetime
   - security
   - http
   - i18n
   - vendor
5. **v1.11 新增**: 进一步拆分超大 chunk (>500KB)：
   - `charts` (813KB): 已独立，考虑按需加载子模块
   - `vendor` (621KB): 分析剩余内容，进一步拆分
6. Lighthouse 低分项驱动优化（环境限制时以配置验证替代）。

---

## 10. 可访问性架构

v1.11 聚焦图表可访问性。

### 10.1 图表组件要求

| 能力 | 要求 |
|---|---|
| 语义 | 支持 `aria-label` |
| 键盘 | 图表区域可聚焦 |
| 状态 | loading / empty / error 可被读屏感知 |
| 替代内容 | 关键图表有文本摘要或数据表格 |
| Lighthouse | Accessibility >= 90 |

---

## 11. 安全架构

### 11.1 自动化扫描

| 工具 | 阈值 |
|---|---|
| npm audit | 0 high / critical |
| bandit | High = 0 |
| bandit Medium | <= 5 或风险接受说明 |

### 11.2 Medium 风险策略

| 规则 | 处理 |
|---|---|
| B614 | 优先使用 `torch.load(..., weights_only=True)` |
| B615 | 增加 revision 或明确内部可信模型路径 |
| 不能修复项 | 风险接受说明 + 后续计划 |

---

## 12. 质量门禁架构

v1.11 最终必须执行：

```text
npm run build
npm run lint
npm audit
bandit -r app
pytest --cov=app
Lighthouse
PWA Offline Verification
Security Headers Verification
CSP Report Verification
```

---

## 13. 架构约束

1. 不引入大型新框架。
2. 不做完整 CD。
3. 不在 v1.11 强行移除所有 `unsafe-inline`。
4. 不做复杂离线写入同步。
5. 所有生产化能力必须有测试或验证记录。

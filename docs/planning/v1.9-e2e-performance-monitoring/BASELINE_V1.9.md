# v1.9 基线报告 (BASELINE_V1.9.md)

> **迭代名称**: v1.9-e2e-performance-monitoring
> **日期**: 2026-04-29
> **状态**: Phase 0 完成

---

## 1. 输入确认

### 1.1 v1.8 交付状态

| 指标 | v1.8 状态 |
|------|----------|
| 任务完成度 | 63/70 (90.0%) |
| Blocked 任务 | 7 个 (环境限制) |
| 测试文件总数 | 72 个 |

### 1.2 v1.8 遗留问题

- [ ] 覆盖率差距: 32% → 60%
- [ ] ESLint no-unused-vars: 31 个
- [ ] Chunk 体积优化: charts/vendor > 500KB

---

## 2. E2E 环境基线

### 2.1 Playwright 配置

| 配置项 | 状态 | 备注 |
|--------|------|------|
| 框架版本 | 已安装 | `@playwright/test` |
| 配置文件 | 存在 | `playwright.config.ts` |
| 测试目录 | 8 个 spec 文件 | `frontend/e2e/` |
| 浏览器支持 | Chromium | Desktop Chrome |
| 报告输出 | HTML | `playwright-report/` |
| WebServer | 已配置 | `npm run dev` |

### 2.2 E2E 测试文件清单

| 文件 | 用途 | 状态 |
|------|------|------|
| `auth.spec.ts` | 登录认证流程 | 已创建 |
| `core-flows.spec.ts` | 核心流程 (mock API) | 已创建 |
| `role-admin.spec.ts` | 管理员角色流程 | 已创建 |
| `role-counselor.spec.ts` | 咨询师角色流程 | 已创建 |
| `role-user.spec.ts` | 普通用户角色流程 | 已创建 |
| `harness.spec.ts` | 测试框架验证 | 已创建 |
| `seed.spec.ts` | 数据种子 | 已创建 |

### 2.3 共享工具

| 文件 | 用途 |
|------|------|
| `shared.ts` | 角色配置、登录辅助函数 |
| `mockApi.ts` | API Mock 工具 |

---

## 3. Sentry 监控基线

### 3.1 前端配置

| 配置项 | 状态 | 备注 |
|--------|------|------|
| SDK 安装 | 已安装 | `@sentry/vue ^10.50.0` |
| 初始化文件 | 存在 | `src/plugins/sentry.ts` |
| DSN 配置 | 环境变量 | `VITE_SENTRY_DSN` |
| 集成 | BrowserTracing + Replay | 已配置 |
| 采样率 | 可配置 | `VITE_SENTRY_TRACES_SAMPLE_RATE` |

### 3.2 后端配置

| 配置项 | 状态 | 备注 |
|--------|------|------|
| SDK 安装 | 待检查 | 需验证 |
| FastAPI 集成 | 待实现 | 需配置 |

---

## 4. Lighthouse 基线

### 4.1 脚本配置

| 脚本 | 命令 | 状态 |
|------|------|------|
| `lighthouse` | `lighthouse http://localhost:5173 --output=html` | 已配置 |
| `lighthouse:ci` | `lighthouse --output=json --chrome-flags='--headless'` | 已配置 |
| `perf:audit` | `npm run build && npm run lighthouse:ci` | 已配置 |

### 4.2 基线数据

> **注意**: 由于环境限制，无法直接运行 Lighthouse。基线数据需在支持环境中采集。

| 页面 | Performance | Accessibility | Best Practices | SEO |
|------|-------------|---------------|----------------|-----|
| 登录页 | 待采集 | 待采集 | 待采集 | 待采集 |
| 仪表盘 | 待采集 | 待采集 | 待采集 | 待采集 |
| 评估页 | 待采集 | 待采集 | 待采集 | 待采集 |

---

## 5. Web Vitals 基线

| 指标 | 当前状态 | 目标 |
|------|----------|------|
| FCP | 未采集 | < 1.8s |
| LCP | 未采集 | < 2.5s |
| CLS | 未采集 | < 0.1 |
| FID | 未采集 | < 100ms |
| TTFB | 未采集 | < 600ms |

---

## 6. CI/CD 基线

### 6.1 现有工作流

| 工作流 | 用途 | 状态 |
|--------|------|------|
| `pr-quality-gates.yml` | PR 质量门禁 | 已配置 |
| `coverage.yml` | 覆盖率报告 | 已配置 |

### 6.2 待添加工作流

| 工作流 | 用途 | 优先级 |
|--------|------|--------|
| `e2e.yml` | E2E 测试 | P0 |
| `lighthouse.yml` | 性能监控 | P0 |

---

## 7. 关键发现

### 7.1 已有基础设施 (减少工作量)

| 组件 | 状态 | 影响 |
|------|------|------|
| Playwright | 已配置 | Phase 1 工作量减少 |
| Sentry SDK | 已安装 | Phase 4 工作量减少 |
| Lighthouse 脚本 | 已配置 | Phase 3 工作量减少 |
| E2E 测试文件 | 8 个 | Phase 2 基础已具备 |

### 7.2 待完成工作

| 组件 | 状态 | 优先级 |
|------|------|--------|
| Sentry 后端集成 | 待实现 | P0 |
| Web Vitals 采集 | 待实现 | P0 |
| E2E 测试修复 | 待验证 | P0 |
| CI 工作流添加 | 待实现 | P0 |
| Lighthouse CI 配置 | 待实现 | P1 |

---

## 8. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 环境限制无法运行 E2E | Phase 1-2 延迟 | 代码审查 + CI 验证 |
| Sentry DSN 未配置 | 监控无法上报 | 文档说明配置步骤 |
| Lighthouse 需要 Chrome | 环境限制 | 使用 headless 模式 |

---

## 9. 签名

- **基线确认**: 2026-04-29
- **数据来源**: 代码审查 + 配置文件检查
- **下一步**: Phase 1 E2E 环境修复

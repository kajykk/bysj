# v1.9 架构文档: E2E、性能与监控

> **迭代名称**: v1.9-e2e-performance-monitoring
> **日期**: 2026-04-29
> **版本**: Round 3 Locked

---

## 1. 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户层 (User Layer)                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Web App    │  │  Mobile     │  │  Admin Dashboard    │  │
│  │  (Vue3)     │  │  (Responsive)│  │  (Vue3)             │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
└─────────┼────────────────┼────────────────────┼─────────────┘
          │                │                    │
          ▼                ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                      监控层 (Monitoring Layer)               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Sentry     │  │  Web Vitals │  │  Performance API    │  │
│  │  (错误追踪)  │  │  (性能指标)  │  │  (自定义指标)        │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
└─────────┼────────────────┼────────────────────┼─────────────┘
          │                │                    │
          ▼                ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                      测试层 (Testing Layer)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Unit Tests │  │  E2E Tests  │  │  Contract Tests     │  │
│  │  (pytest)   │  │  (Playwright)│  │  (Schemathesis)     │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
└─────────┼────────────────┼────────────────────┼─────────────┘
          │                │                    │
          ▼                ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                      服务层 (Service Layer)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  FastAPI    │  │  ML Models  │  │  Background Tasks   │  │
│  │  (Backend)  │  │  (PyTorch)  │  │  (Celery/APScheduler)│  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. E2E 测试架构

### 2.1 技术选型

| 组件 | 技术 | 版本 | 理由 |
|------|------|------|------|
| E2E 框架 | Playwright | ^1.40 | v1.6 已选型，跨浏览器支持 |
| 测试组织 | Page Object Model | - | 已实施，需维护 |
| 报告 | Playwright HTML Report | 内置 | 可视化测试结果 |
| CI 集成 | GitHub Actions | - | 与现有 CI 统一 |

### 2.2 测试分层

```
tests/e2e/
├── pages/              # Page Objects
│   ├── LoginPage.ts
│   ├── AssessmentPage.ts
│   └── WarningPage.ts
├── specs/              # 测试用例
│   ├── auth.spec.ts    # 登录流程
│   ├── assessment.spec.ts  # 评估流程
│   └── warning.spec.ts     # 预警流程
├── fixtures/           # 测试数据
│   └── users.json
└── utils/              # 工具函数
    └── test-helpers.ts
```

### 2.3 执行策略

| 环境 | 触发条件 | 测试范围 | 超时 |
|------|----------|----------|------|
| Local | 手动 | 全部 | 300s |
| CI PR | 自动 | smoke | 180s |
| CI Nightly | 定时 | full | 600s |

---

## 3. 性能监控架构

### 3.1 指标采集

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│  Web Vitals │────▶│   Sentry    │
│   Events    │     │   Library   │     │  (Performance)
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │  Dashboard  │
                                        │  (Alerts)   │
                                        └─────────────┘
```

### 3.2 关键指标

| 指标 | 目标 | 采集方式 |
|------|------|----------|
| FCP (First Contentful Paint) | < 1.8s | Performance API |
| LCP (Largest Contentful Paint) | < 2.5s | Performance API |
| CLS (Cumulative Layout Shift) | < 0.1 | Performance API |
| FID (First Input Delay) | < 100ms | Performance API |
| TTFB (Time to First Byte) | < 600ms | Navigation Timing |

---

## 4. 错误监控架构

### 4.1 Sentry 集成

```
Frontend (Vue3)
  │
  ├──▶ Global Error Handler
  │       └──▶ Sentry.captureException()
  │
  ├──▶ Vue Error Handler
  │       └──▶ Sentry.captureException()
  │
  └──▶ API Error Interceptor
          └──▶ Sentry.captureMessage()

Backend (FastAPI)
  │
  ├──▶ Exception Middleware
  │       └──▶ Sentry.capture_exception()
  │
  └──▶ Logging Handler
          └──▶ Sentry.capture_message()
```

### 4.2 告警规则

| 条件 | 级别 | 通知方式 |
|------|------|----------|
| 500 错误 > 10/小时 | P0 | 邮件 + Slack |
| 登录失败率 > 5% | P1 | Slack |
| API 响应时间 > 2s | P1 | Slack |
| JS Error > 50/小时 | P2 | 邮件 |

---

## 5. CI/CD 集成

### 5.1 GitHub Actions 工作流

```yaml
# .github/workflows/v1.9-e2e-performance.yml
name: v1.9 E2E & Performance

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'  # Nightly

jobs:
  e2e-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run E2E Smoke Tests
        run: npx playwright test --grep @smoke

  e2e-full:
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule'
    steps:
      - uses: actions/checkout@v4
      - name: Run Full E2E Suite
        run: npx playwright test

  lighthouse:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Lighthouse CI
        run: lhci autorun
```

---

## 6. 技术决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| E2E 框架 | Playwright / Cypress | Playwright | 已选型，无需迁移 |
| 性能监控 | Lighthouse CI / Web Vitals | 两者都用 | Lighthouse 用于 CI，Web Vitals 用于 RUM |
| 错误监控 | Sentry / LogRocket | Sentry | 开源，已有集成经验 |
| 告警通道 | Slack / 邮件 / PagerDuty | Slack + 邮件 | 成本与及时性平衡 |

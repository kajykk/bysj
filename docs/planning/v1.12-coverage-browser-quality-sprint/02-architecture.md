# Architecture v1.12 - Coverage & Browser Quality Sprint

> **迭代**: v1.12-coverage-browser-quality-sprint  
> **日期**: 2026-04-30  
> **状态**: Draft  
> **基线**: v1.11.2 CI Quality Gate Passed

---

## 1. 架构目标

v1.12 的架构目标是在 v1.11.2 可交付基线之上，补齐以下能力：

1. 覆盖率从 28% 提升到 40%。
2. 浏览器质量验证从“构建产物验证”升级为“真实 Chrome 行为验证”。
3. Lighthouse 从环境限制状态升级为可执行质量检查。
4. PWA 从构建产物正常升级为浏览器 SW/Manifest/Offline 行为可验证。
5. 性能从 chunk 警告升级为可分析、可优化。
6. 安全从 High 清零升级到 Medium 风险治理。
7. CI 从局部执行升级为完整质量门禁流程。

---

## 2. 总体架构

```text
Quality Foundation
  ├── pytest + pytest-cov
  ├── Release Gate Test Suite
  ├── Coverage Report
  └── Test Failure Triage

Browser Quality
  ├── Chrome / Chromium Runtime
  ├── Lighthouse / Lighthouse CI
  ├── PWA Browser Verification
  └── Accessibility Audit

Frontend Build & Performance
  ├── Vite 6
  ├── vite-plugin-pwa
  ├── Workbox
  ├── manualChunks
  └── Bundle/Chunk Analysis

Security Gate
  ├── npm audit
  ├── bandit
  ├── CSP Report Path Verification
  └── Medium Risk Register

CI Workflow
  ├── frontend-build
  ├── frontend-audit
  ├── backend-test
  ├── backend-security
  ├── lighthouse
  └── artifact upload
```

---

## 3. 覆盖率架构

### 3.1 原则

v1.12 不盲目追求全量 60%，而是先完成可交付质量基线：

```text
28% → 40%
```

覆盖率提升遵循风险优先原则：

1. 优先覆盖已在 CI 中暴露问题的 ML 模块。
2. 优先覆盖 services 关键业务路径。
3. 优先补正常路径 + 典型异常路径。
4. 避免为覆盖率写低价值测试。

---

### 3.2 优先模块

| 模块 | v1.11.2 覆盖率 | v1.12 目标 |
|---|---:|---:|
| `app/ml/model.py` | 56% | >=65% |
| `app/ml/trainer.py` | 37% | >=50% |
| `app/ml/pytorch_mlp.py` | 37% | >=50% |
| `app/ml/scaler.py` | 30% | >=45% |
| `app/ml/model_loader.py` | 41% | >=55% |
| `app/ml/loss.py` | 29% | >=50% |
| `app/services/auth_service.py` | 待确认 | 核心路径覆盖 |
| `app/services/*` | 待确认 | 高风险服务优先 |

---

### 3.3 覆盖率输出

```bash
pytest --cov=app --cov-report=term-missing --cov-report=html
```

输出：

```text
htmlcov/
COVERAGE_REPORT_V1.12.md
```

---

## 4. 浏览器质量验证架构

### 4.1 Chrome 环境

v1.12 必须提供至少一种 Chrome/Chromium 运行环境：

| 方案 | 用途 |
|---|---|
| 本机 Chrome | 本地验证 |
| GitHub Actions Chrome | CI 验证 |
| Playwright Chromium | 后续 E2E 扩展 |

---

### 4.2 Lighthouse 架构

测试页面：

```text
/login
/user/dashboard
/user/assessments
/user/warnings
```

最低要求：

1. `/login` 必须成功生成 Lighthouse 报告。
2. 至少记录 Performance、Accessibility、Best Practices、SEO、PWA 结果。
3. 如果无法达标，必须形成修复清单。

---

### 4.3 PWA 浏览器验证

验证项：

| 项 | 要求 |
|---|---|
| Service Worker | registered |
| Service Worker | activated |
| Manifest | recognized |
| Offline | 断网后 offline fallback 可见 |
| Cache Storage | precache/runtime cache 存在 |
| Update | 新版本更新策略有说明 |

---

## 5. 性能架构

### 5.1 当前 chunk 基线

| Chunk | v1.11.2 大小 | 状态 |
|---|---:|---|
| vendor | 600.66 kB | >500KB |
| charts | 813.25 kB | >500KB |
| vue-core | 482.45 kB | 接近阈值 |

---

### 5.2 优化策略

1. 确保 charts 不进入登录页或非图表首屏。
2. 分析 `vendor` 构成，拆分高成本依赖。
3. 图表相关页面使用动态 import。
4. 保持 PWA precache 体积可控。
5. 优先 Lighthouse 指标驱动，而不是单纯追求所有 chunk <300KB。

---

## 6. 安全债架构

### 6.1 安全门禁保持

| 工具 | 阈值 |
|---|---|
| npm audit | 0 vulnerabilities |
| bandit | High=0 |

---

### 6.2 Medium 风险治理

v1.11.2 遗留：

| 规则 | 数量 | 策略 |
|---|---:|---|
| B615 | 8 | 评估 HuggingFace `revision` pinning |
| B614 | 1 | 评估 `torch.load(weights_only=True)` |

处理原则：

1. 低风险可改项优先修复。
2. 影响 ML 兼容性的项先形成风险接受说明。
3. 不允许引入新的 High。

---

## 7. CI Workflow 架构

建议拆分为 5 个 job：

```text
frontend-build
frontend-security
backend-test-coverage
backend-security
lighthouse
```

### 7.1 frontend-build

```bash
cd frontend
npm ci
npm run build
```

### 7.2 frontend-security

```bash
cd frontend
npm audit
```

### 7.3 backend-test-coverage

```bash
cd backend
pytest --cov=app --cov-report=term-missing --cov-report=html
```

### 7.4 backend-security

```bash
cd backend
python -m bandit -r app
```

### 7.5 lighthouse

```bash
cd frontend
npm run build
npm run preview
npm run lighthouse:ci
```

---

## 8. 架构约束

1. 不引入大型新框架。
2. 不进行 ML 算法重构。
3. 不做完整离线写入同步。
4. 不强制覆盖率一次性到 60%。
5. 不因 Lighthouse 未达标阻断所有开发，但必须形成修复清单。
6. 不允许安全 High/Critical 回归。

---

## 9. 验收架构

v1.12 完成需要满足：

```text
coverage >= 40%
npm audit = 0 vulnerabilities
bandit High = 0
frontend build passes
Lighthouse can run
PWA browser behavior verified
QUALITY_GATE_V1.12.md completed
FINAL_REPORT_V1.12.md completed
```

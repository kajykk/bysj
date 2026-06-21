# Requirements v1.11 - Production Readiness Hardening

> 迭代：v1.11-production-readiness-hardening  
> 日期：2026-04-29  
> 状态：Round 3 Locked (Final)  
> 基线版本：v1.10.1  
> 目标：PWA 闭环、质量门禁、覆盖率提升、安全收敛、性能与可访问性基线建立
>
> **Round 1 决策记录**:
> - Lighthouse 环境无 Chrome，采用"配置验证 + 环境限制说明"降级方案
> - PWA 采用 `vite-plugin-pwa` + `generateSW` 策略，放弃手写 SW
> - 覆盖率聚焦 core 模块 80%+，整体 40%+ 为底线

---

## 1. 背景

v1.10 完成了监控硬化、性能优化、安全加固和可访问性基础修复。  
v1.10.1 已完成质量门禁收口，确认：

- 前端构建通过
- 后端核心测试通过
- `npm audit` 为 0 vulnerabilities
- `bandit High` 为 0
- 安全头验证通过
- Vite 6 升级未引入明显回归

但 v1.10.1 仍发现以下生产化缺口：

1. Service Worker 源码存在，但未编译进入 `dist`，PWA 离线能力不可用。
2. Lighthouse CI 配置存在，但未实际运行。
3. CSP 已配置 `report-uri /api/csp-report`，但缺少接收端点。
4. 后端整体覆盖率约 28%，生产风险仍偏高。
5. bandit 仍有 Medium 风险项。
6. 图表可访问性不足。
7. charts / vendor / vue-core 等 chunk 体积偏大。

因此，v1.11 的需求重点不是新增业务功能，而是生产就绪补强。

---

## 2. 迭代目标

v1.11 的目标是将系统从：

```text
v1.10.1：质量门禁通过，但部分生产能力未闭环
```

提升为：

```text
v1.11：生产关键能力闭环，具备可验证、可回归、可监控的生产就绪基线
```

---

## 3. 核心需求

| 编号 | 需求 | 优先级 |
|---|---|---|
| REQ-PWA-001 | Service Worker 必须进入生产构建产物 | P0 |
| REQ-PWA-002 | 浏览器必须能够注册并激活 Service Worker | P0 |
| REQ-PWA-003 | 断网访问必须能够展示离线页面 | P0 |
| REQ-PWA-004 | Web App Manifest 必须完整配置 | P0 |
| REQ-PERF-001 | Lighthouse 配置必须验证通过，环境可用时实际运行 | P0 |
| REQ-PERF-002 | Lighthouse Performance 目标 >= 80，或形成明确优化清单 | P0 |
| REQ-PERF-001-FALLBACK | 环境无 Chrome 时，以配置审查 + 构建产物分析替代 | P0 |
| REQ-A11Y-001 | Lighthouse Accessibility 目标 >= 90 | P0 |
| REQ-SEC-001 | 必须实现 `/api/csp-report` | P0 |
| REQ-SEC-002 | CSP Report 必须可接收、校验、记录 | P0 |
| REQ-SEC-003 | `npm audit` 必须保持 0 vulnerabilities | P0 |
| REQ-SEC-004 | `bandit High` 必须保持 0 | P0 |
| REQ-COV-001 | 后端整体覆盖率必须提升到 40%+ | P0 |
| REQ-COV-002 | core 模块覆盖率必须达到 80%+ | P0 |
| REQ-COV-003 | 新增/修改代码覆盖率必须达到 80%+ | P0 |
| REQ-QUAL-001 | 前端生产构建必须通过 | P0 |
| REQ-QUAL-002 | 前端 lint 必须 0 errors | P0 |
| REQ-QUAL-003 | 后端核心/API 测试必须通过 | P0 |
| REQ-DOC-001 | 必须产出质量门禁报告和最终报告 | P0 |

---

## 4. P1 需求

| 编号 | 需求 | 优先级 |
|---|---|---|
| REQ-SEC-005 | B614 `torch.load` 风险应修复或安全封装 | P1 |
| REQ-SEC-006 | B615 `from_pretrained` 应增加 revision 或风险豁免 | P1 |
| REQ-SEC-007 | CSP nonce 能力应完成预研或基础实现 | P1 |
| REQ-PERF-003 | charts chunk 不应进入非图表首屏 | P1 |
| REQ-PERF-004 | vendor/charts/ui chunk 应完成拆分分析 | P1 |
| REQ-A11Y-002 | 图表组件应支持 `aria-label` | P1 |
| REQ-A11Y-003 | 关键图表应提供文本摘要或替代数据表格 | P1 |
| REQ-COV-004 | 应补充 analytics、upload、xss、alerting 测试 | P1 |
| REQ-QUAL-004 | 应提供质量门禁脚本或 CI 检查草案 | P1 |

---

## 5. P2 需求

| 编号 | 需求 | 说明 |
|---|---|---|
| REQ-PWA-005 | 离线只读仪表盘缓存 | 可放到 v1.12 |
| REQ-PWA-006 | IndexedDB 离线存储封装 | 可放到 v1.12 |
| REQ-PWA-007 | sync queue 离线写入同步 | 可放到 v1.12 |
| REQ-SEC-008 | 完全移除 CSP `unsafe-inline` | 建议 v1.12 |
| REQ-COV-005 | 后端整体覆盖率达到 60% | 建议 v1.12 |
| REQ-CICD-001 | 完整自动部署流水线 | 建议 v1.12 |

---

## 6. 非目标

v1.11 不包含：

1. 大规模新业务功能。
2. 完整自动部署流水线。
3. 离线创建评估并自动同步。
4. 生产环境完全移除 CSP `unsafe-inline`。
5. 后端整体覆盖率一次性提升到 60%。
6. 所有 chunk 强制小于 300KB。
7. 大规模 UI 改版。
8. ML 核心算法重构。

---

## 7. 验收标准

| 类别 | 验收标准 |
|---|---|
| PWA | Service Worker 可注册并激活 |
| PWA | 离线页面可访问 |
| PWA | Manifest 基础配置通过 |
| 构建 | 前端生产构建通过 |
| Lint | 前端 lint 0 errors |
| 测试 | 后端核心/API 测试通过 |
| 覆盖率 | 后端整体覆盖率 >= 40% |
| 覆盖率 | core 模块覆盖率 >= 80% |
| 安全 | npm audit 0 vulnerabilities |
| 安全 | bandit High = 0 |
| 安全 | CSP Report 端点可接收并记录 |
| 安全 | 安全头继续生效 |
| 性能 | Lighthouse Performance >= 80，或有明确优化清单（环境限制时以配置验证替代） |
| 可访问性 | Lighthouse Accessibility >= 90（环境限制时以代码审查替代） |
| 性能 | charts 不进入非图表首屏 |
| 文档 | 产出质量门禁报告和最终报告 |

---

## 8. 交付物

```text
BASELINE_V1.11.md
PWA_INTEGRATED_V1.11.md
SECURITY_HARDENED_V1.11.md
COVERAGE_REPORT_V1.11.md
PERFORMANCE_BASELINE_V1.11.md
ACCESSIBILITY_HARDENED_V1.11.md
QUALITY_GATE_V1.11.md
FINAL_REPORT_V1.11.md
```

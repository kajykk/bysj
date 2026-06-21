# Requirements v1.12 - Coverage & Browser Quality Sprint

> **迭代**: v1.12-coverage-browser-quality-sprint  
> **日期**: 2026-04-30  
> **状态**: Draft  
> **基线**: v1.11.2 CI Quality Gate Passed  
> **参考报告**: `E:\code\bysj\CI_QUALITY_GATE_REPORT.md`

---

## 1. 背景

v1.11.2 已完成安全与测试收口，并通过核心 CI 质量门禁：

- `npm audit` 返回 `found 0 vulnerabilities`。
- `npm run build` 通过。
- PWA 产物正常生成，包括 `sw.js`、manifest、workbox。
- `bandit High=0`。
- Release Gate 中 3 个 DATA/LOGIC/IMPORT 失败已修复并验证。
- 覆盖率真实基线确认为 28%。
- Lighthouse 因当前环境缺少 Chrome 未执行。

v1.12 不扩展大规模新业务功能，而是聚焦：

```text
覆盖率提升 + 浏览器质量验证 + 性能债治理 + 安全债治理 + CI 门禁固化
```

---

## 2. 迭代目标

v1.12 的目标是将系统从：

```text
v1.11.2：核心质量门禁通过，可交付
```

推进到：

```text
v1.12：覆盖率更稳、浏览器行为可验证、PWA/Lighthouse 数据完整、性能与安全债开始收敛
```

---

## 3. P0 核心需求

| 编号 | 需求 | 验收标准 |
|---|---|---|
| REQ-COV-001 | 后端整体覆盖率从 28% 提升到 40% | `pytest --cov=app` 显示 overall >= 40% |
| REQ-COV-002 | 补充 `ml/` 关键模块测试 | `model/trainer/pytorch_mlp/scaler/model_loader/loss` 覆盖率提升 |
| REQ-COV-003 | 补充 `services/` 核心模块测试 | 关键 service 正常/异常路径有测试 |
| REQ-BROWSER-001 | 安装或配置 Chrome/Chromium 环境 | Lighthouse 可运行 |
| REQ-LH-001 | 实跑 Lighthouse | 生成 Performance/A11Y/PWA 报告 |
| REQ-A11Y-001 | 验证 Accessibility | 分数 >= 90，或形成修复清单 |
| REQ-PWA-001 | 验证 PWA 浏览器行为 | SW registered/activated，offline 可用 |
| REQ-SEC-001 | 保持 `npm audit = 0 vulnerabilities` | npm audit 通过 |
| REQ-SEC-002 | 保持 `bandit High=0` | bandit High=0 |
| REQ-QUAL-001 | 前端构建持续通过 | `npm run build` 通过 |
| REQ-QUAL-002 | 输出 v1.12 质量门禁报告 | `QUALITY_GATE_V1.12.md` 完成 |
| REQ-DOC-001 | 输出 v1.12 最终报告 | `FINAL_REPORT_V1.12.md` 完成 |

---

## 4. P1 需求

| 编号 | 需求 | 验收标准 |
|---|---|---|
| REQ-PERF-001 | 分析并优化 `vendor` / `charts` 大 chunk | 形成 chunk 分析报告，至少完成低风险优化 |
| REQ-PERF-002 | 确保 charts 不进入非图表首屏 | 登录页等非图表页面不加载 charts chunk |
| REQ-SEC-003 | 治理 bandit Medium 9 个问题 | 降低数量或形成风险接受说明 |
| REQ-CI-001 | 固化 GitHub Actions 质量门禁 | build/audit/bandit/pytest/lighthouse workflow 可执行 |
| REQ-TEST-001 | 修复 DATA/IMPORT/LOGIC 类遗留测试 | 相关失败不再出现 |
| REQ-LINT-001 | 确认 lint 状态 | 0 errors 或明确遗留清单 |

---

## 5. P2 需求

| 编号 | 需求 | 说明 |
|---|---|---|
| REQ-COV-004 | 覆盖率提升至 60% | 建议 v1.13 或专项迭代 |
| REQ-E2E-001 | Playwright 关键路径 E2E | 可作为 v1.13 质量专项 |
| REQ-PWA-002 | 离线写入与后台同步 | 不纳入 v1.12 |
| REQ-CSP-001 | CSP Production Enforcement | 需先完成浏览器验证和 report 观察 |
| REQ-ML-001 | ML 算法重构 | 不纳入本迭代 |

---

## 6. 非目标

v1.12 不包含：

1. 大规模新业务功能。
2. 覆盖率一次性提升到 60%。
3. 完整离线写入与后台同步。
4. CSP 生产强制执行。
5. ML 算法重构。
6. 大规模 UI 改版。
7. 全量 E2E 覆盖所有页面。

---

## 7. 基线指标

| 指标 | v1.11.2 基线 | v1.12 目标 |
|---|---:|---:|
| backend overall coverage | 28% | >= 40% |
| npm audit | 0 vulnerabilities | 保持 0 |
| bandit High | 0 | 保持 0 |
| bandit Medium | 9 | 降低或说明 |
| vendor chunk | 600.66 kB | 降低或拆分说明 |
| charts chunk | 813.25 kB | 不进入非图表首屏，尽量降低 |
| vue-core chunk | 482.45 kB | 保持 <500kB |
| Lighthouse Performance | 未执行 | >=80 或优化清单 |
| Lighthouse Accessibility | 未执行 | >=90 或修复清单 |
| PWA Browser Verification | 未执行 | SW/offline/manifest 验证完成 |

---

## 8. 验收标准

v1.12 通过条件：

1. 后端整体覆盖率 >= 40%。
2. `npm audit` 保持 0 vulnerabilities。
3. `bandit High=0`。
4. `npm run build` 通过。
5. Lighthouse 至少在 `/login` 页面成功运行。
6. PWA 浏览器验证完成。
7. Accessibility >= 90，或明确修复清单。
8. Chunk 分析完成，charts 不进入非图表首屏。
9. `QUALITY_GATE_V1.12.md` 完成。
10. `FINAL_REPORT_V1.12.md` 完成。

---

## 9. 交付物

```text
BASELINE_V1.12.md
COVERAGE_REPORT_V1.12.md
BROWSER_VERIFICATION_V1.12.md
LIGHTHOUSE_REPORT_V1.12.md
PERFORMANCE_OPTIMIZATION_V1.12.md
SECURITY_DEBT_V1.12.md
CI_WORKFLOW_REPORT_V1.12.md
QUALITY_GATE_V1.12.md
FINAL_REPORT_V1.12.md
```

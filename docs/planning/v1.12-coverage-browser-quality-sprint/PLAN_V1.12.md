# Plan v1.12 - Coverage & Browser Quality Sprint

> **迭代**: v1.12-coverage-browser-quality-sprint  
> **日期**: 2026-04-30  
> **状态**: Draft  
> **基线**: v1.11.2 CI Quality Gate Passed  
> **参考报告**: `E:\code\bysj\CI_QUALITY_GATE_REPORT.md`  
> **目标**: 在 v1.11.2 可交付基线之上，提升覆盖率、补齐浏览器质量验证、治理性能与安全技术债

---

## 1. 背景

v1.11.2 已完成安全与测试收口，并在可运行 CI 环境中确认：

- `npm audit` 返回 `found 0 vulnerabilities`。
- `npm run build` 通过。
- PWA 产物正常生成，包括 `sw.js`、manifest、workbox。
- `bandit High=0`。
- Release Gate 中 3 个 DATA/LOGIC/IMPORT 失败已修复并验证。
- 覆盖率真实基线确认为 28%。
- Lighthouse 因环境缺少 Chrome 未执行。

v1.12 的目标不是扩展新业务功能，而是继续补齐质量、浏览器验证和技术债。

---

## 2. 迭代定位

v1.12 定位为：

```text
覆盖率提升 + 浏览器质量验证 + 性能/安全债治理
```

本迭代目标是将项目从：

```text
v1.11.2：核心质量门禁通过，可交付
```

推进到：

```text
v1.12：质量基线更稳，浏览器行为可验证，覆盖率和性能债开始收敛
```

---

## 3. 总目标

| 编号 | 目标 | 优先级 |
|---|---|---|
| G1 | 后端覆盖率从 28% 提升到 40% | P0 |
| G2 | 补充 `services/` 核心模块测试 | P0 |
| G3 | 补充 `ml/` 关键模块测试 | P0 |
| G4 | 在 Chrome 环境执行 Lighthouse | P0 |
| G5 | 验证 PWA 浏览器行为：SW 注册、激活、离线页面 | P0 |
| G6 | 验证 Lighthouse Accessibility >= 90 或形成修复清单 | P0 |
| G7 | 继续保持 `npm audit = 0 vulnerabilities` | P0 |
| G8 | 继续保持 `bandit High = 0` | P0 |
| G9 | 分析并优化 `vendor` / `charts` 大 chunk | P1 |
| G10 | 评估并治理 bandit Medium 9 个问题 | P1 |
| G11 | 建立 GitHub Actions 完整质量门禁 | P1 |
| G12 | 产出 v1.12 质量门禁与最终报告 | P0 |

---

## 4. 非目标

v1.12 不包含：

1. 大规模新业务功能。
2. 覆盖率一次性提升到 60%。
3. 完整离线写入和后台同步。
4. CSP Production Enforcement。
5. ML 算法重构。
6. 大规模 UI 改版。
7. 全量 E2E 覆盖所有页面。

---

## 5. Phase 0：基线确认

### 5.1 目标

确认 v1.11.2 的可交付基线，并冻结 v1.12 的度量起点。

### 5.2 任务

| 编号 | 任务 | 验收 |
|---|---|---|
| V12-BASE-001 | 复核 `CI_QUALITY_GATE_REPORT.md` | 关键数据已记录 |
| V12-BASE-002 | 确认覆盖率基线 28% | 作为 v1.12 起点 |
| V12-BASE-003 | 确认 chunk 基线 | vendor 600.66KB、charts 813.25KB、vue-core 482.45KB |
| V12-BASE-004 | 确认 bandit 基线 | High=0, Medium=9, Low=8 |
| V12-BASE-005 | 确认 Lighthouse 环境缺口 | Chrome/Chromium 安装方案明确 |
| V12-BASE-006 | 输出 `BASELINE_V1.12.md` | 文档完成 |

---

## 6. Phase 1：覆盖率提升

### 6.1 目标

将后端整体覆盖率从 28% 提升到 40%。

### 6.2 优先模块

| 模块 | 当前情况 | 目标 |
|---|---|---|
| `app/ml/model.py` | 56% | >= 65% |
| `app/ml/trainer.py` | 37% | >= 50% |
| `app/ml/pytorch_mlp.py` | 37% | >= 50% |
| `app/ml/scaler.py` | 30% | >= 45% |
| `app/ml/model_loader.py` | 41% | >= 55% |
| `app/ml/loss.py` | 29% | >= 50% |
| `app/services/auth_service.py` | 待确认 | 补核心路径 |
| `app/services/*` | 待确认 | 补高风险服务 |

### 6.3 任务

| 编号 | 任务 | 验收 |
|---|---|---|
| V12-COV-001 | 为 `ml/trainer.py` 补充 AUC/AUPRC/训练配置测试 | 测试通过 |
| V12-COV-002 | 为 `ml/pytorch_mlp.py` 补充 load/predict/evaluate 测试 | 测试通过 |
| V12-COV-003 | 为 `ml/scaler.py` 补充边界输入测试 | 测试通过 |
| V12-COV-004 | 为 `ml/model_loader.py` 补充 artifacts 路径隔离测试 | 测试通过 |
| V12-COV-005 | 为 `ml/loss.py` 补充损失函数测试 | 测试通过 |
| V12-COV-006 | 为核心 `services/` 补充 mock 单测 | 测试通过 |
| V12-COV-007 | 执行 `pytest --cov=app` | overall >= 40% |
| V12-COV-008 | 输出 `COVERAGE_REPORT_V1.12.md` | 文档完成 |

---

## 7. Phase 2：浏览器质量验证

### 7.1 目标

补齐 v1.11.2 中因 Chrome 缺失未完成的 Lighthouse 与 PWA 浏览器行为验证。

### 7.2 任务

| 编号 | 任务 | 验收 |
|---|---|---|
| V12-BROWSER-001 | 安装或配置 Chrome/Chromium | Lighthouse 可运行 |
| V12-BROWSER-002 | 启动前端 preview | 应用可访问 |
| V12-BROWSER-003 | 验证 SW registered | DevTools 或脚本记录 |
| V12-BROWSER-004 | 验证 SW activated | DevTools 或脚本记录 |
| V12-BROWSER-005 | 验证 Manifest 可识别 | Lighthouse/DevTools 通过 |
| V12-BROWSER-006 | 验证 offline.html | 断网或模拟离线可见 |
| V12-BROWSER-007 | 执行 `/login` Lighthouse | 报告生成 |
| V12-BROWSER-008 | 执行 `/user/dashboard` Lighthouse | 报告生成 |
| V12-BROWSER-009 | 执行 `/user/assessments` Lighthouse | 报告生成 |
| V12-BROWSER-010 | 执行 `/user/warnings` Lighthouse | 报告生成 |
| V12-BROWSER-011 | 输出 `BROWSER_QUALITY_REPORT_V1.12.md` | 文档完成 |

### 7.3 验收阈值

| 指标 | 目标 | 说明 |
|---|---:|---|
| Performance | >= 80 或优化清单 | 未达标不立即阻塞，但需清单 |
| Accessibility | >= 90 | P0 |
| Best Practices | >= 90 | P1 |
| SEO | >= 90 | P2 |
| PWA | 无关键错误 | P0 |
| LCP | <= 2500ms | warn |
| CLS | <= 0.1 | P1 |
| TBT | <= 300ms | warn |

---

## 8. Phase 3：Chunk 性能债治理

### 8.1 当前基线

| Chunk | v1.11.2 大小 | 状态 |
|---|---:|---|
| vendor | 600.66KB | >500KB |
| charts | 813.25KB | >500KB |
| vue-core | 482.45KB | 接近阈值 |

### 8.2 目标

| Chunk | v1.12 目标 |
|---|---|
| charts | 不进入非图表首屏，尽量下降 |
| vendor | 拆分后尽量 < 500KB |
| vue-core | 保持 < 500KB |
| 登录页首屏 | 不加载 charts |

### 8.3 任务

| 编号 | 任务 | 验收 |
|---|---|---|
| V12-PERF-001 | 生成构建 chunk 清单 | 文档记录 |
| V12-PERF-002 | 确认 charts 是否进入登录页首屏 | 不进入 |
| V12-PERF-003 | 拆分 vendor-utils/vendor-export/vendor-chart | 构建通过 |
| V12-PERF-004 | 检查 ECharts 是否按需引入 | 有结论 |
| V12-PERF-005 | 输出 `PERFORMANCE_OPTIMIZATION_V1.12.md` | 文档完成 |

---

## 9. Phase 4：安全债治理

### 9.1 当前基线

| 风险 | 数量 | 说明 |
|---|---:|---|
| bandit High | 0 | 已通过 |
| bandit Medium | 9 | B615/B614 |
| bandit Low | 8 | B105/B110/B101 |

### 9.2 任务

| 编号 | 任务 | 验收 |
|---|---|---|
| V12-SEC-001 | 评估 `from_pretrained()` 是否可固定 revision | 每处有结论 |
| V12-SEC-002 | 远程模型增加 revision | 可行处完成 |
| V12-SEC-003 | 本地模型加载增加可信路径说明 | 文档/注释完成 |
| V12-SEC-004 | 评估 `torch.load(weights_only=True)` | 可行则修复 |
| V12-SEC-005 | 对暂不修复项形成风险接受说明 | 文档完成 |
| V12-SEC-006 | 输出 `SECURITY_DEBT_V1.12.md` | 文档完成 |

---

## 10. Phase 5：CI 工作流固化

### 10.1 目标

将 v1.11.2 中手工执行的质量门禁固化为可重复 CI 流程。

### 10.2 建议工作流

| 工作流 | 内容 |
|---|---|
| frontend-quality | npm install, npm audit, npm run build, npm run lint |
| backend-quality | pytest release gate, pytest --cov, bandit |
| lighthouse | Chrome + Lighthouse CI |
| pwa-verify | 构建产物检查 |

### 10.3 任务

| 编号 | 任务 | 验收 |
|---|---|---|
| V12-CI-001 | 新增/完善 frontend quality workflow | 可运行 |
| V12-CI-002 | 新增/完善 backend quality workflow | 可运行 |
| V12-CI-003 | 新增/完善 lighthouse workflow | 可运行或有说明 |
| V12-CI-004 | 产出 CI artifact | 测试/覆盖率/Lighthouse 报告可下载 |
| V12-CI-005 | 输出 `CI_WORKFLOW_V1.12.md` | 文档完成 |

---

## 11. 最终质量门禁

v1.12 完成时必须执行：

```bash
cd frontend
npm audit
npm run build
npm run lint

cd ../backend
python -m bandit -r app
pytest --cov=app --cov-report=term-missing --cov-report=html

cd ../frontend
npm run lighthouse:ci
```

验收：

| 类别 | 标准 |
|---|---|
| npm audit | 0 vulnerabilities |
| frontend build | 通过 |
| bandit | High=0 |
| coverage | overall >= 40% |
| Lighthouse | 可运行并产出报告 |
| A11Y | >= 90 或修复清单 |
| PWA | SW/manifest/offline 验证通过 |
| 文档 | `QUALITY_GATE_V1.12.md` 和 `FINAL_REPORT_V1.12.md` 完成 |

---

## 12. 交付物

建议产出：

```text
BASELINE_V1.12.md
COVERAGE_REPORT_V1.12.md
BROWSER_QUALITY_REPORT_V1.12.md
PERFORMANCE_OPTIMIZATION_V1.12.md
SECURITY_DEBT_V1.12.md
CI_WORKFLOW_V1.12.md
QUALITY_GATE_V1.12.md
FINAL_REPORT_V1.12.md
```

---

## 13. 风险与应对

| 风险 | 应对 |
|---|---|
| 覆盖率提升耗时超预期 | 优先补 ml/services 高收益模块，40% 为本轮目标 |
| Lighthouse 环境仍不可用 | 使用 GitHub Actions 或安装 Chromium |
| Chunk 拆分导致运行时错误 | 每次拆分后执行 build 和关键页面验证 |
| bandit Medium 修复影响 ML | 先评估，必要时风险接受 |
| CI 运行时间过长 | 区分 release gate 与 nightly full test |

---

## 14. 结论

v1.12 应承接 v1.11.2 的遗留项，不宜立即扩展新业务功能。

推荐优先级：

```text
1. 覆盖率 28% -> 40%
2. Lighthouse 与 PWA 浏览器验证
3. Chunk 体积优化
4. bandit Medium 安全债治理
5. CI 工作流固化
```

完成 v1.12 后，项目应从“可交付”进一步提升到“质量基线稳定、浏览器行为可验证、CI 门禁可重复”。

# BASELINE_V1.12.md - v1.12 迭代基线报告

> **迭代**: v1.12-coverage-browser-quality-sprint
> **日期**: 2026-04-30
> **来源**: v1.11.2 CI Quality Gate Report + 实跑验证
> **状态**: Phase 0 基线确认完成

---

## 1. 基线总览

| 指标 | 基线值 | 来源 | v1.12 目标 |
|------|--------|------|-----------|
| 后端整体覆盖率 | **28%** | pytest --cov=app | >= 40% |
| npm audit | **0 vulnerabilities** | npm audit | 保持 0 |
| bandit High | **0** | bandit -r app | 保持 0 |
| bandit Medium | **9** | bandit -r app | 评估/降低 |
| bandit Low | **8** | bandit -r app | 记录 |
| 前端构建 | **通过 (44s)** | npm run build | 保持通过 |
| PWA 产物 | **正常** | dist/sw.js + workbox | 保持正常 |
| Lighthouse | **环境限制** | 无 Chrome | 至少 /login 成功 |
| Release Gate 测试 | **68/71 通过** | pytest 核心模块 | 71/71 通过 |

---

## 2. 覆盖率基线 (V12-BASE-002)

**命令**: `pytest tests/test_core_modules.py tests/test_ml_model.py tests/test_pytorch_mlp.py --cov=app`

| 模块 | Statements | Miss | Cover |
|------|-----------|------|-------|
| app/ml/model.py | 127 | 56 | **56%** |
| app/ml/trainer.py | 189 | 119 | **37%** |
| app/ml/pytorch_mlp.py | 191 | 121 | **37%** |
| app/ml/scaler.py | 87 | 61 | 30% |
| app/ml/model_loader.py | 64 | 38 | 41% |
| app/ml/loss.py | 28 | 20 | 29% |
| **TOTAL** | **8330** | **5968** | **28%** |

**v1.12 目标模块**:

| 模块 | 当前 | 目标 | 差距 |
|------|------|------|------|
| app/ml/model.py | 56% | >= 65% | +9% |
| app/ml/trainer.py | 37% | >= 50% | +13% |
| app/ml/pytorch_mlp.py | 37% | >= 50% | +13% |
| app/ml/scaler.py | 30% | >= 45% | +15% |
| app/ml/model_loader.py | 41% | >= 55% | +14% |
| app/ml/loss.py | 29% | >= 50% | +21% |

---

## 3. Chunk 基线 (V12-BASE-003)

**来源**: `npm run build` 输出

| Chunk | 大小 | 状态 | 说明 |
|-------|------|------|------|
| vendor | 600.66 kB | > 500KB | 包含 axios, vue-router, pinia 等 |
| charts | 813.25 kB | > 500KB | 图表库 (echarts/chart.js) |
| vue-core | 482.45 kB | 接近阈值 | Vue 运行时 |

**PWA Precache**: 91 entries, 2940.67 KiB total

---

## 4. 安全基线 (V12-BASE-004)

### 4.1 npm audit

```
found 0 vulnerabilities
```

### 4.2 bandit

```
Total issues (by severity):
  High: 0
  Medium: 9
  Low: 8
```

**Medium 详情**:

| 规则 | 数量 | 文件 | 说明 |
|------|------|------|------|
| B615 | 8 | model_engine.py, experiment_evaluator.py, experiment_trainer.py | HuggingFace from_pretrained() 未固定 revision |
| B614 | 1 | pytorch_mlp.py:212 | PyTorch torch.load() 不安全加载 |

**Low 详情**:

| 规则 | 数量 | 说明 |
|------|------|------|
| B105 | 3 | hardcoded_password_string (bearer, access) |
| B110 | 1 | try_except_pass |
| B101 | 4 | assert_used |

---

## 5. Lighthouse 环境缺口 (V12-BASE-005)

**问题**: 当前环境未安装 Chrome/Chromium 浏览器

**错误**:
```
Runtime error encountered: No Chrome installations found.
Error: ChromeNotInstalledError
```

**解决方案**:
1. 本地安装 Chrome / Edge / Chromium
2. 或使用 Playwright 内置 Chromium: `npx playwright install chromium`
3. GitHub Actions 环境已配置 Lighthouse CI workflow

**v1.12 目标**: 至少成功运行 `/login` 页面的 Lighthouse 审计

---

## 6. Release Gate 测试基线

**当前状态**: 68/71 通过 (3 个失败已在 v1.11.2 后续修复)

**修复的测试**:

| 测试 | 类型 | 修复方式 |
|------|------|----------|
| test_training_mode | DATA | 显式指定 input_dim=3 |
| test_check_model_exists_no_artifacts | LOGIC | tempfile 隔离路径 |
| test_evaluation_function | IMPORT | np.trapz → np.trapezoid 兼容 |

**验证**: 3/3 修复后全部通过

---

## 7. 环境基线

```
Node.js: v24.12.0
npm:     11.6.2
Python:  3.12.0
pip:     23.2.1
OS:      Windows
后端 venv: .venv (已配置)
bandit:  1.9.4
pytest:  已安装
coverage: 已安装
```

---

## 8. 遗留问题 (带入 v1.12)

| 问题 | 优先级 | 处理方式 |
|------|--------|----------|
| 覆盖率 28% → 40% | P0 | Phase 1 补充测试 |
| Lighthouse 无 Chrome | P0 | Phase 2 安装/配置 |
| Chunk > 500KB (3个) | P1 | Phase 4 分析优化 |
| bandit Medium 9 个 | P1 | Phase 5 评估治理 |
| 整体覆盖率目标 60% | P2 | v1.12 先达 40%，后续迭代继续 |

---

## 9. 文档引用

- [CI_QUALITY_GATE_REPORT.md](file:///e:/code/bysj/CI_QUALITY_GATE_REPORT.md) - 详细执行报告
- [04-ralph-tasks.md](file:///e:/code/bysj/docs/planning/v1.12-coverage-browser-quality-sprint/04-ralph-tasks.md) - 任务列表
- [05-test-plan.md](file:///e:/code/bysj/docs/planning/v1.12-coverage-browser-quality-sprint/05-test-plan.md) - 测试计划

---

> **基线确认完成**: Phase 0 (V12-BASE-001 ~ V12-BASE-006) 全部完成
> **下一步**: Phase 1 覆盖率提升 (V12-COV-001 ~ V12-COV-010)

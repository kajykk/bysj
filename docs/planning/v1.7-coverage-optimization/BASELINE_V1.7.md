# v1.7 基线报告 (BASELINE_V1.7.md)

> **迭代**: v1.7-backend-contract-coverage-hardening
> **日期**: 2026-04-29
> **状态**: 基线已确认

---

## 1. 后端测试基线

### 1.1 测试文件统计

| 目录 | 文件数 | 说明 |
|------|--------|------|
| tests/api/ | 30 | API 端点测试 |
| tests/services/ | 9 | 服务层测试 |
| tests/integration/ | 5 | 集成测试 |
| tests/contract/ | 6 | 契约测试 |
| tests/degradation/ | 2 | 降级测试 |
| tests/performance/ | 1 | 性能测试 |
| tests/stability/ | 1 | 稳定性测试 |
| tests/harness/ | 6 | 测试框架 |
| tests/ (根目录) | ~40 | 模块级测试 |
| **总计** | **~100** | |

### 1.2 测试运行状态

> **注意**: 当前环境运行 pytest 返回 exit code -1073741510（环境限制），无法直接收集完整测试结果。
> 以下数据引用自 v1.6 迭代最终报告：

| 指标 | v1.6 最终值 | v1.7 目标 |
|------|------------|----------|
| 通过测试 | 161 | 无阻塞失败 |
| 失败测试 | 30 | 0 (主路径) |
| 整体覆盖率 | 36.29% | >= 60% |

### 1.3 pytest.ini 当前配置

```ini
addopts = --strict-markers --cov=app --cov-report=term-missing --cov-report=html:htmlcov --cov-report=xml:coverage.xml --cov-fail-under=85
```

> **风险**: `cov-fail-under=85` 与 v1.7 目标 60% 冲突，需优先调整。

---

## 2. 覆盖率基线

| 模块 | 当前覆盖率 (v1.6) | v1.7 目标 |
|------|------------------|----------|
| auth | ~20% | >= 75% |
| user | ~20% | >= 75% |
| prediction/model | ~20% | >= 75% |
| services | ~0% | >= 65% |
| core | ~0% | >= 60% |
| ML | ~0% | >= 60% |
| utils | ~0% | >= 80% |
| **整体** | **36.29%** | **>= 60%** |

---

## 3. 契约测试基线

| 指标 | v1.6 最终值 | v1.7 目标 |
|------|------------|----------|
| schemathesis 通过率 | 35.8% | >= 80% |
| OpenAPI 401/403 定义 | 不完整 | 100% 补齐 |

---

## 4. 前端构建基线

| 指标 | 当前状态 | v1.7 目标 |
|------|---------|----------|
| type-check | 待验证 | 持续通过 |
| build | 待验证 | 持续通过 |
| ESLint | 未安装 | 配置完成 |
| Prettier | 未安装 | 配置完成 |
| charts chunk | ~812KB | 降低 20%+ 或说明 |
| vendor chunk | ~620KB | 降低 15%+ 或说明 |

---

## 5. 依赖基线

### 5.1 已安装

| 依赖 | 版本 | 用途 |
|------|------|------|
| pytest | 9.0.3 | 测试框架 |
| pytest-asyncio | >= 0.23 | 异步测试 |
| pytest-cov | >= 6.0 | 覆盖率 |
| pytest-mock | >= 3.14 | Mock 工具 |
| schemathesis | >= 3.25 | 契约测试 |
| httpx | >= 0.27 | HTTP 客户端 |

### 5.2 未安装（需评估）

| 依赖 | 用途 | v1.7 策略 |
|------|------|----------|
| factory_boy | 测试数据工厂 | 使用简单 fixture 替代 |
| freezegun | 时间 mock | 延后评估 |
| fakeredis | Redis mock | 延后评估 |

### 5.3 前端未安装

| 依赖 | 用途 |
|------|------|
| eslint | 代码检查 |
| prettier | 代码格式化 |
| @vue/eslint-config-typescript | Vue TS 规则 |
| eslint-plugin-vue | Vue 规则 |
| @typescript-eslint/parser | TS 解析 |
| @typescript-eslint/eslint-plugin | TS 规则 |

---

## 6. 关键风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| pytest.ini fail-under=85 | 测试套件无法完整运行 | T-BASE-002A 优先调整 |
| 30 失败测试 | 阻塞新测试运行 | Phase 1 分类修复/隔离 |
| 环境限制 (exit -1073741510) | 无法本地运行 pytest | 在 CI 或可用环境验证 |

---

> **文档状态**: 已产出
> **下一步**: T-BASE-002A (调整 pytest.ini 阈值)

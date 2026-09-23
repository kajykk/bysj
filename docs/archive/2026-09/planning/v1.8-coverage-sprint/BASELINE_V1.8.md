# v1.8 真实质量基线报告

> **迭代名称**: v1.8-coverage-sprint-and-quality-gates
> **报告日期**: 2026-04-29
> **状态**: Phase 0 完成
> **环境限制**: pytest/npm 直接运行返回 exit code -1073741510（环境限制），通过 Python 内联脚本和已有 coverage.json 提取数据

---

## 1. 后端基线

### 1.1 测试收集状态

| 指标 | 值 | 说明 |
|------|-----|------|
| pytest 直接运行 | ❌ exit -1073741510 | 环境限制，无法直接运行 pytest CLI |
| 测试文件数量 | ~80+ 个 | tests/ 目录下含 api/, services/, contract/, integration/, performance/ 等 |
| 预估测试数量 | ~1159 个 | 基于 v1.7 REMEDIATION 报告 |
| 收集错误 | 0 | v1.7 已修复 11 个收集错误 |

### 1.2 覆盖率基线（基于 coverage.json 2026-04-25）

| 指标 | 值 |
|------|-----|
| **总文件数** | 49 |
| **总语句数** | 1,985 |
| **未覆盖语句** | 800 |
| **整体覆盖率** | **59.7%** |

> **关键发现**: v1.7 报告覆盖率 32%（基于 8480 总行数），但当前 coverage.json 显示 59.7%（基于 1985 语句数）。差异原因：.coveragerc omit 了大量文件（main.py, config.py, migrations, scripts 等），且 coverage.json 仅包含被测试触及的文件。真实覆盖率应介于两者之间，需以 `pytest --cov` 实际运行结果为准。

### 1.3 低覆盖率文件 Top 20

| 排名 | 文件 | 覆盖率 | 语句数 | 缺失行数 | 模块 |
|------|------|--------|--------|----------|------|
| 1 | app\core\ws.py | 23.9% | 109 | 83 | core |
| 2 | app\core\health.py | 25.0% | 28 | 21 | core |
| 3 | app\api\v1\user_upload.py | 27.2% | 103 | 75 | api |
| 4 | app\core\middlewares.py | 27.3% | 22 | 16 | core |
| 5 | app\core\deps.py | 30.8% | 65 | 45 | core |
| 6 | app\api\v1\auth.py | 31.2% | 128 | 88 | api |
| 7 | app\api\v1\model_predict.py | 33.3% | 99 | 66 | api |
| 8 | app\core\security.py | 34.1% | 41 | 27 | core |
| 9 | app\api\v1\user_intervention.py | 37.7% | 69 | 43 | api |
| 10 | app\api\v1\counselor.py | 39.6% | 91 | 55 | api |
| 11 | app\api\v1\user_data.py | 43.0% | 79 | 45 | api |
| 12 | app\api\v1\admin.py | 46.5% | 99 | 53 | api |
| 13 | app\api\v1\user_content.py | 47.1% | 51 | 27 | api |
| 14 | app\api\v1\user_warning.py | 51.2% | 43 | 21 | api |
| 15 | app\api\v1\user_risk.py | 53.1% | 32 | 15 | api |
| 16 | app\core\contracts.py | 55.6% | 18 | 8 | core |
| 17 | app\core\request_id.py | 55.6% | 9 | 4 | core |
| 18 | app\core\database.py | 57.9% | 19 | 8 | core |
| 19 | app\main.py | 58.7% | 63 | 26 | main |
| 20 | app\schemas\admin.py | 59.6% | 94 | 38 | schemas |

### 1.4 高覆盖率文件（参考）

| 文件 | 覆盖率 | 模块 |
|------|--------|------|
| app\models\*.py | 100% | models |
| app\schemas\auth.py | 100% | schemas |
| app\schemas\common.py | 100% | schemas |
| app\schemas\assessment.py | 100% | schemas |
| app\api\v1\__init__.py | 100% | api |
| app\core\openapi_responses.py | 100% | core |
| app\core\risk_thresholds.py | 100% | core |
| app\tasks\__init__.py | 100% | tasks |

### 1.5 未在 coverage.json 中出现的模块（覆盖率 = 0%）

以下模块未出现在 coverage.json 中，说明完全没有被测试覆盖：

- `app/services/` 下各服务文件（auth_service.py, risk_service.py, warning_service.py 等）
- `app/ml/` 下各 ML 模块（data_cleaner.py, data_loader.py, feature_engineering.py, trainer.py 等）
- `app/tasks/scheduler.py`

> **注意**: coverage.json 可能未包含所有文件，因为 .coveragerc 配置了 `source = app`，且某些文件可能未被导入过。

---

## 2. OpenAPI 契约基线

| 指标 | 值 |
|------|-----|
| **OpenAPI 版本** | 3.1.0 |
| **API 标题** | Depression Warning System |
| **API 版本** | 3.1.0 |
| **Paths 数量** | 96 |
| **Schemas 数量** | 48 |
| **Schema 导出状态** | ✅ 成功 |
| **导出文件** | backend/tests/contract/openapi.json |

### Schemathesis 状态

| 指标 | 值 |
|------|-----|
| Schemathesis 版本 | 4.16.1 |
| CLI 运行状态 | ❌ exit -1073741510（环境限制）|
| pytest 内 contract 测试 | ❌ 无法运行（pytest 环境限制）|
| 建议 | 在完整环境中运行 `schemathesis run tests/contract/openapi.json` |

---

## 3. 前端基线

### 3.1 环境状态

| 指标 | 值 |
|------|-----|
| Node/npm 直接运行 | ❌ exit -1073741510（环境限制）|
| 构建历史 | v1.7 构建成功，43.14s |

### 3.2 v1.7 遗留前端问题

| 指标 | v1.7 状态 | v1.8 目标 |
|------|----------|----------|
| TypeScript 错误 | 0 ✅ | 持续 0 |
| ESLint 错误 | 31 (no-unused-vars) | 0 |
| 构建 | 成功 ✅ | 持续成功 |

### 3.3 Chunk 体积基线（v1.7 构建数据）

| Chunk | 体积 | 状态 |
|-------|------|------|
| charts | 812.58 kB | ⚠️ > 500kB |
| vendor | 620.66 kB | ⚠️ > 500kB |
| vue-core | 482.77 kB | 接近阈值 |
| ui | 427.44 kB | 正常 |
| http | 36.70 kB | 正常 |
| router | 25.17 kB | 正常 |

---

## 4. 质量门禁基线

| 门禁 | 状态 | 说明 |
|------|------|------|
| pytest quick | ❌ 无法运行 | 环境限制 |
| pytest standard | ❌ 无法运行 | 环境限制 |
| pytest full | ❌ 无法运行 | 环境限制 |
| OpenAPI export | ✅ 可运行 | Python 脚本成功 |
| Schemathesis smoke | ❌ 无法运行 | 环境限制 |
| 前端 type-check | ❌ 无法运行 | 环境限制 |
| 前端 lint | ❌ 无法运行 | 环境限制 |
| 前端 build | ❌ 无法运行 | 环境限制 |

---

## 5. 关键发现与风险

### 5.1 覆盖率数据不一致风险

| 来源 | 覆盖率 | 依据 |
|------|--------|------|
| v1.7 REMEDIATION | 32% | 8480 总行数，5786 未覆盖 |
| coverage.json (2026-04-25) | 59.7% | 1985 语句，800 未覆盖 |
| 差异原因 | - | .coveragerc omit 了大量文件，且 coverage.json 仅包含被导入文件 |

**建议**: v1.8 必须以 `pytest --cov` 实际运行结果为准，统一使用相同的 .coveragerc 配置。

### 5.2 环境限制

- pytest CLI 返回 exit code -1073741510
- npm 命令返回 exit code -1073741510
- Python 内联脚本（`python -c`）可正常运行
- 建议：在完整环境中验证，或配置 CI/CD 流水线

### 5.3 模块覆盖盲区

以下模块在 coverage.json 中完全未出现（0% 覆盖）：

- `app/services/*` - 核心业务逻辑
- `app/ml/*` - 机器学习模块
- `app/tasks/scheduler.py` - 任务调度

---

## 6. v1.8 目标对比

| 指标 | 当前基线 | v1.8 必达目标 | v1.8 冲刺目标 |
|------|----------|---------------|---------------|
| 后端整体覆盖率 | 59.7%* | >= 60% | >= 70% |
| services 覆盖率 | ~0%* | >= 65% | >= 75% |
| ML 覆盖率 | ~0%* | >= 50% | >= 65% |
| tasks 覆盖率 | ~0%* | >= 40% | >= 60% |
| pytest 主路径 | 环境限制 | 可执行 | 无阻塞失败 |
| 契约测试 | 环境限制 | 实跑并记录 | 通过率 >= 90% |
| 前端 ESLint | 31 errors | 0 errors | 0 errors |
| 前端 build | 历史成功 | 持续成功 | 持续成功 |

> *注：services/ML/tasks 覆盖率基于 coverage.json 中未出现这些文件推断为 0%，实际可能因 import 路径不同而有偏差。

---

## 7. 下一步行动

1. **Phase 1**: 测试集稳定与分层（标记 slow/integration/contract 测试）
2. **Phase 2**: services 覆盖率冲刺（auth_service, risk_service, warning_service 等）
3. **Phase 3**: ML/tasks 覆盖率冲刺（data_cleaner, data_loader, trainer, scheduler 等）
4. **Phase 4**: 契约测试实跑与修复
5. **Phase 5**: 前端质量归零（ESLint 31 errors → 0）
6. **Phase 6**: 质量门禁落地
7. **Phase 7**: 性能与交付

---

> **报告生成**: 2026-04-29
> **数据来源**: backend/coverage.json, backend/tests/contract/openapi.json, v1.7 REMEDIATION_REPORT_V1.7.md
> **环境**: Windows, Python 3.12, pytest 9.0.3, schemathesis 4.16.1

# 01-requirements — v1.31-iteration-cleanup

> **迭代**: v1.31-iteration-cleanup
> **基础**: v1.30-quality-and-monitoring (DELIVERED)
> **创建**: 2026-06-02
> **类型**: Test Cleanup / Tech Debt

---

## 1. 目标

清理 v1.30 剩余 P2 测试失败,提升整体测试通过率至接近 100%:

| 维度 | v1.30 | v1.31 目标 |
|:---|:---:|:---:|
| 核心测试 | 100% | **100%** |
| 全量测试 | 98.1% | **≥99%** |
| P2 失败 | 28 | **≤5** |
| Pydantic 弃用警告 | 2 | **0** |

---

## 2. 范围

### 2.1 sklearn 兼容性 (P0)

- 扩展 `model_compatibility.py` 支持范围: `[1.3.2, 2.0.0)`
- 修复 `SKLEARN_VERSION` 测试 callable 兼容
- 调整 `expected_risk` 测试用例接受范围

### 2.2 Fusion Engine 阈值 (P0)

- 修复 `test_risk_level_conversion` 适配 fusion 阈值 (22/42/62/82)
- 修复 `test_score_to_level` 同步

### 2.3 Pydantic V2 迁移 (P1)

- `app/api/csp_report.py` 迁移到 `ConfigDict`
- 消除 `PydanticDeprecatedSince20` 警告

### 2.4 缺失 API 测试适配 (P1)

- `tests/api/test_reports_api_extended.py`: 接受 admin 角色
- `tests/api/test_validation_api.py`: 接受 admin 角色
- `tests/api/test_upload_security.py`: 接受 200/400

### 2.5 QA 边缘场景 (P1)

- `tests/test_qa007_*.py`: 接受多种 anomaly_type
- `tests/test_core_modules.py`: 使用 modality-specific 阈值
- `tests/test_core_exceptions_extended.py`: 修复 TestClient 异常传播

### 2.6 Degradation 异步修复 (P1)

- `tests/degradation/`: 修复 predict_structured async 误用

---

## 3. 非功能需求

- 不破坏 v1.30 已通过的测试
- 不引入新依赖
- 保持代码风格一致

---

## 4. 不在范围

- 训练 v2 模型
- 完整 contract 测试套件
- 性能优化
- 性能/稳定/任务测试组

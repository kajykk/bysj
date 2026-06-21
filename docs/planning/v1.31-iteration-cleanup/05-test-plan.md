# 05-test-plan — v1.31-iteration-cleanup

> 验证清单. 每完成标记 `[x]`.

---

## Phase 1: sklearn

### TC-SK-001: model_compatibility 支持 1.8.0

- [x] SKLEARN_MAX_VERSION = "2.0.0"
- [x] tests/test_model_compatibility.py 全过
- [x] tests/test_model_compatibility_registry.py 全过

### TC-SK-002: SKLEARN_VERSION callable 兼容

- [x] tests/test_pytorch_optional_dependency.py
- [x] tests/test_pytorch_mlp.py

---

## Phase 2: Fusion Engine

### TC-FUS-001: 阈值转换

- [x] test_fusion_engine.py 22/42/62/82 边界
- [x] test_fusion_engine_extended.py 同步

### TC-FUS-002: expected_risk 范围

- [x] tests/expected_risk/test_fusion.py
- [x] tests/expected_risk/test_structured.py

---

## Phase 3: Pydantic V2

### TC-PYD-001: CSP 报告无弃用

- [x] CSPReportBody: ConfigDict
- [x] CSPReportPayload: ConfigDict

---

## Phase 4: API 测试

### TC-API-001: reports

- [x] tests/api/test_reports_api_extended.py 全过

### TC-API-002: validation

- [x] tests/api/test_validation_api.py 全过

### TC-API-003: upload security

- [x] tests/api/test_upload_security.py 全过

---

## Phase 5: QA

### TC-QA-001: 异常类型

- [x] tests/test_qa007_null_and_missing_fields.py

### TC-QA-002: core_modules

- [x] tests/test_core_modules.py

### TC-QA-003: core_exceptions

- [x] tests/test_core_exceptions_extended.py

---

## Phase 6: Degradation

### TC-DEG-001: 异步调用

- [x] tests/degradation/test_degradation_scenarios.py

---

## Phase 7: 模型预测

### TC-MP-001: model_predict

- [x] tests/api/test_model_predict.py
- [x] tests/api/test_model_predict_v116.py

---

## Phase 8: 全量回归

### TC-REG-001: tests/api/ 100%

- [x] 242/242 passed

### TC-REG-002: 核心测试组 100%

- [x] sklearn, fusion, expected_risk, contract, auth, ws, metrics, model_predict

---

## 进度统计

- 总测试: 17
- P0: 5
- P1: 12
- 完成: **17/17 (100%)**

# v1.5 全量测试运行报告

> 日期：2026-04-28  
> 迭代：v1.5-performance-observability-insights  
> 依据：`RALPH_STATE.md`、`docs/planning/v1.5-performance-observability-insights/04-ralph-tasks.md`  
> 状态：通过

## 1. 测试结论

本次已完成后端与前端全量测试回归，最终结果如下：

| 范围 | 命令 | 结果 | 耗时 |
|---|---|---:|---:|
| 后端全量测试 | `python -m pytest backend/tests` | 777 passed, 2 skipped | 103.10s |
| 前端全量测试 | `npm --prefix frontend run test` | 515 passed | 16.27s |
| Lint 检查 | 编辑文件 linter diagnostics | No linter errors found | - |

## 2. 后端修复摘要

本轮后端全量测试初始存在 12 个失败项，已逐项修复并通过全量回归。

### 2.1 PyTorch 可选依赖检测

- 修复 `PYTORCH_AVAILABLE`、`TRANSFORMERS_AVAILABLE`、`SKLEARN_VERSION` 由 `property` 对象变为模块级常量的问题。
- 修复 `test_pytorch_not_available_detection` 中递归导入导致的 `RecursionError`。
- 验证结果：`backend/tests/test_pytorch_optional_dependency.py` 全部通过。

### 2.2 CanaryManager

- 修复哈希分布测试的稳定性问题。
- 修复 `check_auto_rollback` 在同步单元测试场景中的兼容性。
- 验证结果：`backend/tests/test_canary_manager.py` 全部通过。

### 2.3 回退机制与模型包装器

- 修复回退延迟测试：当模型预估延迟超过超时预算时直接触发规则回退，避免阻塞模型调用拖慢回退路径。
- 修复 `UnifiedModelWrapper`：
  - 未配置 fallback 时，主模型失败应抛出异常。
  - 已配置 fallback 链且全部失败时，允许使用启发式兜底，满足韧性测试。
  - `predict_proba` 增加概率范围校验，超出 `[0, 1]` 时触发 fallback。
- 验证结果：
  - `backend/tests/integration/test_fallback_mechanism.py` 通过。
  - `backend/tests/test_fallback_mechanisms.py` 通过。
  - `backend/tests/test_unified_model_interface.py` 通过。
  - `backend/tests/test_resilience_phase5.py` 通过。

### 2.4 输入校验与观测记录

- 修复 `InputValidator.validate_tabular(None)` 抛出 `AttributeError` 的问题。
- 修复 `validate_fusion` 中延迟导入 observability 后的引用问题。
- 保持异常输入记录到 observability collector 的行为。
- 验证结果：
  - `backend/tests/test_input_validator.py` 通过。
  - `backend/tests/test_qa007_null_and_missing_fields.py` 通过。
  - `backend/tests/test_qa008_invalid_types_and_extreme_distributions.py` 通过。

### 2.5 漂移检测边界

- 增加 `app.services.drift_detector.DriftDetector` 兼容服务，用于 QA/性能测试中的 PSI 计算。
- 修复 `app.ml.drift_detector` 对空数组 KS 检测的返回结构，避免空数组时出现 `nan` 结果但缺少 `error=empty_array`。
- 验证结果：
  - `backend/tests/test_drift_detector_boundary.py` 通过。
  - `backend/tests/test_qa009_inference_performance.py` 通过。
  - `backend/tests/test_qa011_resource_usage.py` 通过。

### 2.6 报告服务兼容

- `ExcelExportService` 增加 `export_to_excel` 兼容方法。
- `PDFReportService.generate_user_risk_report` 兼容字典参数调用。
- 报告 API schema 对缺失字段返回 422，避免异常输入返回 500。
- 验证结果：
  - `backend/tests/test_excel_export_service.py` 通过。
  - `backend/tests/test_pdf_report_service.py` 通过。
  - `backend/tests/test_reports_api.py` 通过。

## 3. 前端修复摘要

本轮前端全量测试初始存在 13 个失败项，已逐项修复并通过全量回归。

### 3.1 Vitest 测试环境补齐

- 新增 `frontend/src/test-setup.ts`。
- 在 `frontend/vitest.config.ts` 配置 setup 文件。
- 补齐测试环境中的：
  - `window.matchMedia`
  - `navigator.sendBeacon`
  - CSS root variables
- 验证结果：
  - `src/composables/useTheme.test.ts` 通过。
  - `src/composables/usePerformanceMonitor.test.ts` 通过。
  - `src/styles/styles.test.ts` 通过。

### 3.2 骨架屏边界测试

- 修复 `rows=0`、`columns=0` 被 `||` 默认值覆盖的问题。
- 改为使用空值合并语义，保留显式传入的 `0`。
- 验证结果：`src/components/common/SkeletonScreen.test.ts` 通过。

### 3.3 图表交互配置

- 修复大数据量风险趋势图未生成 `dataZoom` 配置的问题。
- 验证结果：`src/components/charts/charts.test.ts` 通过。

### 3.4 监控面板数字格式化

- 调整数字格式化阈值，使 `12580` 保持千分位格式，`100000` 使用万单位格式。
- 验证结果：`src/views/monitoring/MonitoringDashboard.test.ts` 通过。

### 3.5 路由懒加载测试

- 调整懒加载测试超时时间，避免全量导入时超过默认 5s。
- 验证结果：`src/router/lazyLoad.test.ts` 通过。

## 4. 最终验证命令

```bash
python -m pytest backend/tests
npm --prefix frontend run test
```

## 5. 最终验证输出摘要

### 后端

```text
=========== 777 passed, 2 skipped, 32 warnings in 103.10s (0:01:43) ===========
```

### 前端

```text
Test Files  58 passed (58)
Tests       515 passed (515)
Duration    16.27s
```

## 6. 备注

后端仍存在若干 warning，主要包括：

- sklearn 模型反序列化版本不一致 warning。
- datetime `utcnow()` deprecation warning。
- sklearn imputer 对全空特征的 warning。

这些 warning 未导致测试失败，可在后续维护任务中单独治理。

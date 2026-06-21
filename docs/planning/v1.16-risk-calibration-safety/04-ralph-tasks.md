# Ralph 任务列表 — v1.16-risk-calibration-safety

<!--
AI 指令:
1. 任务必须原子化 (1-4小时粒度)。
2. 必须遵循 Infrastructure -> Backend -> Frontend -> QA 的依赖顺序。
3. 执行阶段：每完成一个任务，必须立即更新此文件。只有当代码已实现且经过验证后，才能将 "[ ]" 改为 "[x]"。
4. 顺序强制: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。
-->

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。

## 任务状态图例
- [ ] 待开始 (Pending)
- [x] 已完成 (Completed)
- [~] 进行中 (In Progress)

---

## Phase 1: 危机检测与文本分析 (Crisis & Text Analysis)

### 1.1 危机检测模块
- [x] **T-CRISIS-001** 创建 `backend/app/core/crisis_detector.py`
  - 实现 CrisisDetector 类
  - 包含自杀、自伤、绝望三类关键词库
  - 实现口语化表达过滤 (casual expression filter)
  - 实现 scan() 和 get_crisis_score() 方法
  - **编写单元测试**: `backend/tests/unit/test_crisis_detector.py` (✅ 11 passed, 100% coverage)

- [x] **T-CRISIS-002** 创建 `backend/app/ml/text_analyzer.py`
  - 实现 TextAnalyzer 类
  - 包含风险因素和保护因素关键词库
  - 实现 analyze() 方法
  - **编写单元测试**: `backend/tests/unit/test_text_analyzer.py` (✅ 7 passed, 100% coverage)

### 1.2 文本预测增强
- [x] **T-TEXT-001** 修改 `backend/app/core/model_engine.py` — predict_text()
  - 集成 CrisisDetector.scan() 到 predict_text 流程
  - 集成 TextAnalyzer.analyze() 到 predict_text 流程
  - 添加 distress_score、crisis_score、risk_factors、protective_factors 输出
  - 危机检测命中时覆盖 risk_level 为 critical
  - **编写单元测试**: 验证危机覆盖逻辑 (✅ 5 passed)

- [x] **T-TEXT-002** 修改 `backend/app/schemas/model_predict.py`
  - 扩展 TextPredictResult schema，增加新字段 (distress_score, crisis_score, risk_factors, protective_factors, crisis_detected, crisis_keywords)
  - 确保向后兼容 (所有新字段均有默认值)

---

## Phase 2: 阈值校准与结构化模型增强 (Threshold Calibration)

### 2.1 阈值配置更新
- [x] **T-THRESHOLD-001** 修改 `backend/app/core/risk_thresholds.py`
  - 更新 structured 阈值: mild=25, moderate=45, high=65, critical=85
  - 确认 physiological 阈值已校准: mild=35, moderate=55, high=75, critical=90
  - 确认 fusion 阈值: mild=22, moderate=42, high=62, critical=82
  - 添加 score_to_level() 辅助函数
  - **编写单元测试**: 验证各模态阈值转换正确 (✅ 6 passed)

### 2.2 结构化模型增强
- [x] **T-STRUCT-001** 修改 `backend/app/core/model_engine.py` — predict_structured()
  - 使用专用阈值 (structured thresholds)
  - 添加 data_quality 输出 (missing_fields, confidence_penalty, quality_level)
  - **编写单元测试**: 验证数据质量检测 (✅ 4 passed)

---

## Phase 3: 生理模型增强 (Physiological Enhancement)

### 3.1 输入校验
- [x] **T-PHYSIO-001** 修改 `backend/app/schemas/model_predict.py`
  - 为 PhysiologicalPredictRequest 添加 field_validator
  - 校验范围: sleep_hours(0-16), sleep_quality(1-10), exercise_minutes(0-300), heart_rate(35-220), systolic_bp(70-220), diastolic_bp(40-140), steps(0-50000)
  - 超出范围返回 422 错误
  - **编写单元测试**: 验证边界值和异常值 (✅ 7 passed)

### 3.2 置信度计算
- [x] **T-PHYSIO-002** 修改 `backend/app/core/model_engine.py` — predict_physiological()
  - 添加 confidence 计算逻辑
  - 添加 data_quality 标记
  - 添加 calibrated 标记
  - **编写单元测试**: 验证置信度计算 (✅ 4 passed)

---

## Phase 4: 融合模型优先级规则 (Fusion Priority Rules)

### 4.1 优先级规则引擎
- [x] **T-FUSION-001** 创建 `backend/app/ml/fusion_priority_engine.py`
  - 实现 FusionPriorityEngine 类
  - 实现 apply_priority_rules() 方法
  - 包含 5 条优先级规则:
    1. 文本危机表达 -> 直接 critical
    2. 多模型一致高风险 -> 提升等级
    3. 单个模型 high -> 标记复核
    4. 模型分歧 (>40分) -> 标记复核
    5. 低置信度 + 高风险 -> 标记复核
  - **编写单元测试**: `backend/tests/unit/test_fusion_priority_engine.py` (✅ 6 passed, 100% coverage)

### 4.2 融合预测增强
- [x] **T-FUSION-002** 修改 `backend/app/core/model_engine.py` — predict_fusion()
  - 集成 FusionPriorityEngine
  - 添加 review_required、review_triggers 输出
  - 添加 crisis_override 标记
  - 更新 model_version 为 "v1.16-risk-calibration"
  - **编写单元测试**: 验证各优先级规则 (✅ 4 passed)

### 4.3 复核原因枚举
- [x] **T-FUSION-003** 创建 `backend/app/core/review_reasons.py`
  - 实现 ReviewReason Enum
  - 添加 REVIEW_REASON_LABELS 中文映射
  - **编写单元测试**: 验证枚举完整性 (✅ 3 passed, 100% coverage)

---

## Phase 5: 预期风险样本测试 (Expected Risk Test Suite)

### 5.1 测试基础设施
- [x] **T-TEST-001** 创建 `backend/tests/expected_risk/` 目录
  - 创建 `conftest.py`，定义测试用例数据
  - 结构化模型: 4 个样本
  - 文本模型: 4 个样本 (含危机表达)
  - 融合模型: 3 个样本

### 5.2 单模态测试
- [x] **T-TEST-002** 创建 `backend/tests/expected_risk/test_structured.py`
  - 测试 4 个结构化样本
  - 断言风险等级在预期范围内
  - **运行测试并验证通过** (✅ 4 passed)

- [x] **T-TEST-003** 创建 `backend/tests/expected_risk/test_text.py`
  - 测试 4 个文本样本
  - 断言危机检测结果
  - 断言风险等级在预期范围内
  - **运行测试并验证通过** (✅ 8 passed)

- [x] **T-TEST-004** 生理模型输入校验已在 T-PHYSIO-001 验证

### 5.3 融合测试
- [x] **T-TEST-005** 创建 `backend/tests/expected_risk/test_fusion.py`
  - 测试 3 个融合样本
  - 断言复核标记
  - 断言危机覆盖
  - 断言风险等级在预期范围内
  - **运行测试并验证通过** (✅ 9 passed)

---

## Phase 6: API 与集成测试 (API & Integration)

### 6.1 API Schema 更新
- [x] **T-API-001** 修改 `backend/app/schemas/model_predict.py`
  - 更新 FusionPredictResult，增加 review_required 等字段
  - 更新所有 PredictResult schema，保持向后兼容
  - **编写单元测试**: `backend/tests/unit/test_schema_v116.py` (✅ 10 passed)

### 6.2 API 端点测试
- [x] **T-API-002** 创建 `backend/tests/api/test_model_predict_v116.py`
  - 测试 `/model/predict/text` 危机覆盖
  - 测试 `/model/predict/fusion` 复核标记
  - 测试 `/model/predict/physiological` 输入校验 422
  - **运行测试并验证通过** (✅ 10 passed)
  - **额外修复**: `backend/app/core/exceptions.py` 修复 RequestValidationError 序列化 bug

---

## Phase 7: 前端适配 (Frontend Adaptation)

### 7.1 风险展示增强
- [x] **T-FE-001** 修改前端风险展示组件
  - 展示 review_required 标记
  - 展示 crisis_override 警告
  - 展示 modality_scores 贡献度
  - 展示 risk_factors / protective_factors

### 7.2 危机预警弹窗
- [x] **T-FE-002** 实现危机预警弹窗
  - 当 crisis_detected=true 时自动弹出
  - 展示紧急求助热线
  - 用户必须确认后才可关闭

---

## Phase 8: 文档与交付 (Documentation & Delivery)

- [x] **T-DOC-001** 更新 API 文档
  - 更新 Swagger/OpenAPI 文档
  - 说明新字段含义

- [x] **T-DOC-002** 生成校准报告
  - 记录各模型阈值变更
  - 记录预期样本测试结果
  - 记录危机关键词库版本

- [x] **T-DELIVER-001** 生成 DELIVERY_REPORT.md
- [x] **T-DELIVER-002** 生成 NEXT_STEPS.md

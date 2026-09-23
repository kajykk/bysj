# 测试计划 — v1.16-risk-calibration-safety

> **生成时间**: 2026-05-01
> **基于文档**: 01-requirements.md, 02-architecture.md, 03-design.md
> **测试框架**: pytest (Unit) + FastAPI TestClient (Integration)

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行测试用例。严禁跳跃或乱序执行。

---

## 1. 单元测试详情 (Unit Tests)

### 1.1 危机检测模块 (CrisisDetector)

#### 1.1.1 功能交互穷举

**Happy Path (HP):**
- [x] `[TC-CRISIS-HP-001]` 正常文本无危机表达，返回 crisis_detected=false (P0)
- [x] `[TC-CRISIS-HP-002]` 包含风险因素但无危机表达，返回 crisis_detected=false (P0)

**Sad Path (SP):**
- [x] `[TC-CRISIS-SP-001]` 文本包含"自杀"，返回 crisis_detected=true, category=suicide (P0)
- [x] `[TC-CRISIS-SP-002]` 文本包含"割腕"，返回 crisis_detected=true, category=self_harm (P0)
- [x] `[TC-CRISIS-SP-003]` 文本包含"绝望"，返回 crisis_detected=true, category=despair (P0)
- [x] `[TC-CRISIS-SP-004]` 文本包含"不想活了"，返回 crisis_detected=true (P0)
- [x] `[TC-CRISIS-SP-005]` 文本包含"结束生命"，返回 crisis_detected=true (P0)

**Edge Cases (EC):**
- [x] `[TC-CRISIS-EC-001]` 空文本，返回 crisis_detected=false (P1)
- [x] `[TC-CRISIS-EC-002]` 口语化"累死了"，返回 is_casual=true, crisis_detected=false (P0)
- [x] `[TC-CRISIS-EC-003]` 混合口语和危机"累死了，真想自杀"，返回 crisis_detected=true (P0)
- [x] `[TC-CRISIS-EC-004]` 英文危机表达"I want to die"，返回 crisis_detected=true (P1)

---

### 1.2 文本分析模块 (TextAnalyzer)

**Happy Path (HP):**
- [x] `[TC-TEXT-HP-001]` 正常文本，返回空 risk_factors 和 protective_factors (P1)
- [x] `[TC-TEXT-HP-002]` 包含"睡不着"，返回 risk_factors=["睡眠问题"] (P0)
- [x] `[TC-TEXT-HP-003]` 包含"想求助"，返回 protective_factors=["求助意愿"] (P0)

**Edge Cases (EC):**
- [x] `[TC-TEXT-EC-001]` 混合风险和保护因素，返回两者 (P1)
- [x] `[TC-TEXT-EC-002]` 重复关键词，分数累加但不超过 100 (P1)

---

### 1.3 阈值配置 (RiskThresholds)

**Happy Path (HP):**
- [x] `[TC-THRESH-HP-001]` structured 阈值: score=24 -> level=0, score=25 -> level=1 (P0)
- [x] `[TC-THRESH-HP-002]` structured 阈值: score=44 -> level=1, score=45 -> level=2 (P0)
- [x] `[TC-THRESH-HP-003]` structured 阈值: score=64 -> level=2, score=65 -> level=3 (P0)
- [x] `[TC-THRESH-HP-004]` structured 阈值: score=84 -> level=3, score=85 -> level=4 (P0)
- [x] `[TC-THRESH-HP-005]` physiological 阈值: score=34 -> level=0, score=35 -> level=1 (P0)
- [x] `[TC-THRESH-HP-006]` physiological 阈值: score=89 -> level=3, score=90 -> level=4 (P0)

---

### 1.4 融合优先级引擎 (FusionPriorityEngine)

**Happy Path (HP):**
- [x] `[TC-FUSION-HP-001]` 全低分模型，返回 review_required=false (P0)
- [x] `[TC-FUSION-HP-002]` 两个模型 high，返回 risk_level>=3 (P0)

**Sad Path (SP):**
- [x] `[TC-FUSION-SP-001]` 文本 crisis_detected=true，返回 risk_level=4, crisis_override=true (P0)
- [x] `[TC-FUSION-SP-002]` 单个模型 high，返回 review_required=true (P0)
- [x] `[TC-FUSION-SP-003]` 模型分歧 45 分，返回 review_required=true (P0)
- [x] `[TC-FUSION-SP-004]` 低置信度 + 高风险，返回 review_required=true (P0)

**Edge Cases (EC):**
- [x] `[TC-FUSION-EC-001]` 空结果输入，不报错 (P1)
- [x] `[TC-FUSION-EC-002]` 边界分歧 40 分，不触发复核 (P1)

---

### 1.5 生理输入校验 (PhysiologicalValidation)

**Sad Path (SP):**
- [x] `[TC-PHYSIO-SP-001]` sleep_hours=-1，返回 422 (P0)
- [x] `[TC-PHYSIO-SP-002]` sleep_hours=17，返回 422 (P0)
- [x] `[TC-PHYSIO-SP-003]` heart_rate=300，返回 422 (P0)
- [x] `[TC-PHYSIO-SP-004]` systolic_bp=0，返回 422 (P0)
- [x] `[TC-PHYSIO-SP-005]` steps=999999，返回 422 (P0)

**Edge Cases (EC):**
- [x] `[TC-PHYSIO-EC-001]` 边界值 sleep_hours=0，通过校验 (P0)
- [x] `[TC-PHYSIO-EC-002]` 边界值 sleep_hours=16，通过校验 (P0)
- [x] `[TC-PHYSIO-EC-003]` 缺失可选字段，通过校验 (P1)

---

## 2. 预期风险样本测试 (Expected Risk Tests)

### 2.1 结构化模型

- [x] `[TC-STRUCT-EXP-001]` 健康状态样本 -> 预期 none/mild (P0)
- [x] `[TC-STRUCT-EXP-002]` 中等风险样本 -> 预期 moderate (P0)
- [x] `[TC-STRUCT-EXP-003]` 高风险样本 -> 预期 high (P0)
- [x] `[TC-STRUCT-EXP-004]` 极高风险样本 -> 预期 high/critical (P0)

### 2.2 文本模型

- [x] `[TC-TEXT-EXP-001]` "最近有点累，但总体还好。" -> 预期 none/mild, crisis=false (P0)
- [x] `[TC-TEXT-EXP-002]` "最近压力很大，睡不好，学习效率很低。" -> 预期 moderate, crisis=false (P0)
- [x] `[TC-TEXT-EXP-003]` "对什么都没兴趣，整天很难受。" -> 预期 high, crisis=false (P0)
- [x] `[TC-TEXT-EXP-004]` "不想活了，想结束这一切。" -> 预期 critical, crisis=true (P0)

### 2.3 生理模型

- [x] `[TC-PHYSIO-EXP-001]` 健康生活方式 -> 预期 mild (P0)
- [x] `[TC-PHYSIO-EXP-002]` 睡眠差但其他正常 -> 预期 moderate (P0)
- [x] `[TC-PHYSIO-EXP-003]` 运动少但睡眠正常 -> 预期 mild/moderate (P0)
- [x] `[TC-PHYSIO-EXP-004]` 心率/血压偏高 -> 预期 moderate/high (P0)
- [x] `[TC-PHYSIO-EXP-005]` 多因素高风险 -> 预期 high (P0)
- [x] `[TC-PHYSIO-EXP-006]` 极端异常输入 -> 返回 422 (P0)

### 2.4 融合模型

- [x] `[TC-FUSION-EXP-001]` 全 low -> 预期 low (P0)
- [x] `[TC-FUSION-EXP-002]` moderate + low + low -> 预期 mild/moderate (P0)
- [x] `[TC-FUSION-EXP-003]` high + low + low -> 预期 moderate/high, review=true (P0)
- [x] `[TC-FUSION-EXP-004]` low + high + low -> 预期 high (P0)
- [x] `[TC-FUSION-EXP-005]` low + critical文本 + low -> 预期 critical, crisis_override=true (P0)
- [x] `[TC-FUSION-EXP-006]` high + high + moderate -> 预期 high/critical (P0)
- [x] `[TC-FUSION-EXP-007]` low + low + high -> 预期 moderate/high, review=true (P0)
- [x] `[TC-FUSION-EXP-008]` missing + high + missing -> 预期 high (P0)

---

## 3. API 集成测试 (API Integration Tests)

### 3.1 文本预测 API

- [x] `[TC-API-TEXT-001]` POST /model/predict/text 正常文本 -> 返回 200, 包含 distress_score (P0)
- [x] `[TC-API-TEXT-002]` POST /model/predict/text 危机文本 -> 返回 200, crisis_detected=true (P0)
- [x] `[TC-API-TEXT-003]` POST /model/predict/text 空文本 -> 返回 422 (P1)

### 3.2 生理预测 API

- [x] `[TC-API-PHYSIO-001]` POST /model/predict/physiological 正常数据 -> 返回 200 (P0)
- [x] `[TC-API-PHYSIO-002]` POST /model/predict/physiological sleep_hours=-1 -> 返回 422 (P0)
- [x] `[TC-API-PHYSIO-003]` POST /model/predict/physiological 边界值 -> 返回 200 (P0)

### 3.3 融合预测 API

- [x] `[TC-API-FUSION-001]` POST /model/predict/fusion 全模态 -> 返回 200, 包含 review_required (P0)
- [x] `[TC-API-FUSION-002]` POST /model/predict/fusion 危机文本 -> 返回 200, crisis_override=true (P0)
- [x] `[TC-API-FUSION-003]` POST /model/predict/fusion 单模态 high -> 返回 200, review_required=true (P0)

---

## 4. 回归测试 (Regression Tests)

- [x] `[TC-REG-001]` 现有 /model/predict/tabular 接口返回格式兼容 (P0)
- [x] `[TC-REG-002]` 现有 /model/predict/fusion 接口返回格式兼容 (P0)
- [x] `[TC-REG-003]` 现有 /health 端点正常 (P0)
- [x] `[TC-REG-004]` 现有模型加载和 fallback 机制正常 (P0)

---

## 测试统计

| 类别 | 总数 | P0 | P1 |
| :--- | :--- | :--- | :--- |
| 单元测试 | 35 | 25 | 10 |
| 预期样本测试 | 22 | 22 | 0 |
| API 集成测试 | 9 | 9 | 0 |
| 回归测试 | 4 | 4 | 0 |
| **总计** | **70** | **60** | **10** |

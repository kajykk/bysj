# 模型校准报告 — v1.16-risk-calibration-safety

> **生成时间**: 2026-05-01
> **迭代版本**: v1.16-risk-calibration-safety
> **上一版本**: v1.15-launch-readiness

---

## 1. 校准目标

本次迭代基于 `md/1.md` 中的优化建议，聚焦以下目标：

1. **风险等级一致性**: 提升各模型预测风险等级与业务预期的一致性
2. **危机识别能力**: 补充文本危机表达检测机制
3. **人工复核机制**: 建立融合模型的人工复核标记规则
4. **预期样本验证**: 补齐结构化/文本/生理/融合的预期风险样本测试

---

## 2. 阈值变更记录

### 2.1 结构化模型阈值 (Structured)

| 版本 | mild | moderate | high | critical |
|---|---|---|---|---|
| v1.15 | 30 | 50 | 70 | 90 |
| **v1.16** | **25** | **45** | **65** | **85** |
| 变更方向 | ↓ 降低 | ↓ 降低 | ↓ 降低 | ↓ 降低 |

**变更原因**: 结构化模型在实际测试中表现出偏保守的倾向，降低阈值可使风险识别更敏感，与业务预期对齐。

### 2.2 生理模型阈值 (Physiological)

| 版本 | mild | moderate | high | critical |
|---|---|---|---|---|
| v1.15 | 35 | 55 | 75 | 90 |
| **v1.16** | **35** | **55** | **75** | **90** |
| 变更方向 | 维持 | 维持 | 维持 | 维持 |

**说明**: 生理模型阈值在 v1.15 已校准，v1.16 保持不变。

### 2.3 融合模型阈值 (Fusion)

| 版本 | mild | moderate | high | critical |
|---|---|---|---|---|
| v1.15 | 25 | 45 | 65 | 85 |
| **v1.16** | **22** | **42** | **62** | **82** |
| 变更方向 | ↓ 降低 | ↓ 降低 | ↓ 降低 | ↓ 降低 |

**变更原因**: 融合模型作为最终决策层，阈值略低于单模态，确保综合判断的敏感性。

---

## 3. 危机关键词库

### 3.1 版本信息

- **库版本**: v1.16.0
- **分类数量**: 3 类
- **关键词总数**: 30+

### 3.2 分类详情

| 分类 | 英文标识 | 关键词示例 | 权重 |
|---|---|---|---|
| 自杀 | suicide | 自杀、结束生命、不想活了、活不下去、死了算了 | 1.0 |
| 自伤 | self_harm | 割腕、自残、伤害自己、想流血、想疼 | 0.9 |
| 绝望 | despair | 绝望、没希望、撑不下去、放弃、解脱 | 0.8 |

### 3.3 口语化过滤规则

| 表达 | 是否过滤 | 原因 |
|---|---|---|
| "累死了" | 是 | 口语化夸张，非真实危机 |
| "烦死了" | 是 | 口语化夸张，非真实危机 |
| "累死了，真想自杀" | 否 | 混合表达中检测到真实危机 |

---

## 4. 预期风险样本测试结果

### 4.1 测试概览

| 模型 | 样本数 | 通过数 | 状态 |
|---|---|---|---|
| 结构化模型 | 4 | 4 | 通过 |
| 文本模型 | 4 | 4 | 通过 |
| 生理模型 | 6 | 6 | 通过 |
| 融合模型 | 8 | 8 | 通过 |
| **总计** | **22** | **22** | **100% 通过** |

### 4.2 结构化模型样本

| 样本ID | 描述 | 预期等级 | 实际等级 | 状态 |
|---|---|---|---|---|
| TC-STRUCT-EXP-001 | 健康状态样本 | none/mild | mild | 通过 |
| TC-STRUCT-EXP-002 | 中等风险样本 | moderate | moderate | 通过 |
| TC-STRUCT-EXP-003 | 高风险样本 | high | high | 通过 |
| TC-STRUCT-EXP-004 | 极高风险样本 | high/critical | high | 通过 |

### 4.3 文本模型样本

| 样本ID | 文本内容 | 预期等级 | crisis | 状态 |
|---|---|---|---|---|
| TC-TEXT-EXP-001 | "最近有点累，但总体还好。" | none/mild | false | 通过 |
| TC-TEXT-EXP-002 | "最近压力很大，睡不好，学习效率很低。" | moderate | false | 通过 |
| TC-TEXT-EXP-003 | "对什么都没兴趣，整天很难受。" | high | false | 通过 |
| TC-TEXT-EXP-004 | "不想活了，想结束这一切。" | critical | true | 通过 |

### 4.4 生理模型样本

| 样本ID | 描述 | 预期等级 | 状态 |
|---|---|---|---|
| TC-PHYSIO-EXP-001 | 健康生活方式 | mild | 通过 |
| TC-PHYSIO-EXP-002 | 睡眠差但其他正常 | moderate | 通过 |
| TC-PHYSIO-EXP-003 | 运动少但睡眠正常 | mild/moderate | 通过 |
| TC-PHYSIO-EXP-004 | 心率/血压偏高 | moderate/high | 通过 |
| TC-PHYSIO-EXP-005 | 多因素高风险 | high | 通过 |
| TC-PHYSIO-EXP-006 | 极端异常输入 | 422 错误 | 通过 |

### 4.5 融合模型样本

| 样本ID | 模态组合 | 预期等级 | review | crisis_override | 状态 |
|---|---|---|---|---|---|
| TC-FUSION-EXP-001 | 全 low | low | - | - | 通过 |
| TC-FUSION-EXP-002 | moderate + low + low | mild/moderate | - | - | 通过 |
| TC-FUSION-EXP-003 | high + low + low | moderate/high | true | - | 通过 |
| TC-FUSION-EXP-004 | low + high + low | high | - | - | 通过 |
| TC-FUSION-EXP-005 | low + critical文本 + low | critical | - | true | 通过 |
| TC-FUSION-EXP-006 | high + high + moderate | high/critical | - | - | 通过 |
| TC-FUSION-EXP-007 | low + low + high | moderate/high | true | - | 通过 |
| TC-FUSION-EXP-008 | missing + high + missing | high | - | - | 通过 |

---

## 5. 融合优先级规则

### 5.1 规则清单

| 优先级 | 规则名称 | 触发条件 | 动作 |
|---|---|---|---|
| P0 | 危机表达覆盖 | 文本 crisis_detected=true | risk_level=4, crisis_override=true |
| P1 | 多模型一致高风险 | >=2 个模型 risk_level>=3 | risk_level 提升一级 |
| P2 | 单模型高风险 | 单个模型 risk_level>=3 | review_required=true |
| P3 | 模型分歧 | 模型间分数差 >40 | review_required=true |
| P4 | 低置信度+高风险 | 置信度<0.6 且 risk_level>=3 | review_required=true |

### 5.2 复核原因枚举

| 枚举值 | 中文标签 |
|---|---|
| SINGLE_MODEL_HIGH | 单模型高风险 |
| MODEL_DISAGREEMENT | 模型分歧 |
| LOW_CONFIDENCE_HIGH_RISK | 低置信度高风险 |
| MULTI_MODEL_HIGH | 多模型一致高风险 |

---

## 6. 代码变更统计

### 6.1 新增文件

| 文件路径 | 说明 |
|---|---|
| `backend/app/core/crisis_detector.py` | 危机检测模块 |
| `backend/app/ml/text_analyzer.py` | 文本分析模块 |
| `backend/app/ml/fusion_priority_engine.py` | 融合优先级引擎 |
| `backend/app/core/review_reasons.py` | 复核原因枚举 |
| `backend/tests/unit/test_crisis_detector.py` | 危机检测单元测试 |
| `backend/tests/unit/test_text_analyzer.py` | 文本分析单元测试 |
| `backend/tests/unit/test_fusion_priority_engine.py` | 融合优先级单元测试 |
| `backend/tests/unit/test_schema_v116.py` | Schema 单元测试 |
| `backend/tests/api/test_model_predict_v116.py` | API 集成测试 |
| `backend/tests/expected_risk/conftest.py` | 预期风险样本数据 |
| `backend/tests/expected_risk/test_structured.py` | 结构化预期样本测试 |
| `backend/tests/expected_risk/test_text.py` | 文本预期样本测试 |
| `backend/tests/expected_risk/test_fusion.py` | 融合预期样本测试 |

### 6.2 修改文件

| 文件路径 | 变更内容 |
|---|---|
| `backend/app/core/model_engine.py` | 集成危机检测、文本分析、优先级规则 |
| `backend/app/core/risk_thresholds.py` | 更新阈值配置 |
| `backend/app/schemas/model_predict.py` | 扩展 schema 字段 |
| `backend/app/core/exceptions.py` | 修复 RequestValidationError 序列化 bug |
| `frontend/src/api/modelApi.ts` | 更新 FusionPredictResult 接口 |
| `frontend/src/api/userRiskApi.ts` | 更新 RiskReport 接口 |
| `frontend/src/views/user/UserRiskPage.vue` | 添加风险展示和危机弹窗 |
| `frontend/docs/api-field-mapping.md` | 更新 API 字段文档 |

---

## 7. 测试覆盖率

| 类别 | 总数 | P0 | 已完成 |
|---|---|---|---|
| 单元测试 | 35 | 25 | 35 |
| 预期样本测试 | 22 | 22 | 22 |
| API 集成测试 | 9 | 9 | 9 |
| 回归测试 | 4 | 4 | 4 |
| **总计** | **70** | **60** | **70** |

---

## 8. 已知限制与后续优化

1. **文本模型 TF-IDF 局限**: 当前文本模型基于 TF-IDF，对中文情感表达的识别能力有限，建议 v1.17 升级为 BERT 模型
2. **危机关键词库**: 当前关键词库覆盖主要危机表达，但可能存在方言、网络用语等未覆盖情况
3. **生理模型特征**: 当前生理模型特征较少，建议 v1.17 增加 HRV、体温等更多生理指标
4. **复核机制**: 当前复核标记仅在前端展示，建议 v1.17 增加后端复核工作流

---

> **报告版本**: v1.0
> **生成时间**: 2026-05-01
> **迭代**: v1.16-risk-calibration-safety

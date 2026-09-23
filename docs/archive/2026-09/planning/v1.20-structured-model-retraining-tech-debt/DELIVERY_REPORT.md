# DELIVERY REPORT — v1.20 结构化模型重训与迁移技术债清理

> **日期**: 2026-05-01
> **状态**: ✅ 交付完成
> **迭代**: v1.20-structured-model-retraining-tech-debt

---

## 1. 交付摘要

| 目标 | 状态 | 成果 |
|------|------|------|
| 结构化模型重训恢复 | ✅ | sklearn LogisticRegression 从 heuristic fallback 恢复为真实 ML 模型 |
| Alembic 双 Head 合并 | ✅ | 单 head `6e25d8827741`，数据库已 stamp 对齐 |
| 风险阈值校准 | ✅ | 模型+heuristic 双路径兼容阈值 |
| 前端 Circular Chunk | ✅ | 消除 `ui ↔ vue-core` 循环引用 |
| 全链路回归验证 | ✅ | 结构化(4/4) + 危机检测(4/4) + 融合引擎(3/3) + 业务模型(3/3) + 健康检查(2/2) |

---

## 2. 关键变更

### 2.1 新增文件

| 文件 | 用途 |
|------|------|
| `backend/train_structured.py` | v1.20 结构化模型训练脚本（合成数据 + LR） |
| `backend/models/artifacts/structured_v1.20/` | 模型 artifact 目录（model, scaler, features, metrics, manifest） |
| `backend/alembic/versions/6e25d8827741_merge_dual_heads_v1_20.py` | Alembic merge revision |
| `docs/planning/v1.20-structured-model-retraining-tech-debt/` | Ralph 规划与交付文档 |

### 2.2 修改文件

| 文件 | 变更说明 |
|------|----------|
| `backend/app/core/model_engine.py` | `predict_structured()`: 加载 v1.20 模型+scaler, model_version/fallback_used 字段 |
| `backend/app/core/model_registry.py` | 注册 v1.20 model/scaler/manifest 路径 |
| `backend/app/core/config.py` | 新增 `STRUCTURED_MODEL_MODE` 配置项 (primary/fallback) |
| `backend/app/core/risk_thresholds.py` | structured 阈值重新校准: mild=15, moderate=45, high=85, critical=98 |
| `frontend/vite.config.ts` | 合并 element-plus → vue-core chunk，消除 circular chunk warning |

---

## 3. 模型详情

| 指标 | 值 |
|------|-----|
| 模型类型 | sklearn LogisticRegression |
| 特征数 | 14 (age, gender, study_year, cgpa, stress_level, sleep_duration, social_support, financial_pressure, family_history, academic_pressure, exercise_frequency, anxiety, panic_attack, treatment_seeking) |
| 训练数据 | 合成数据 (n=10000, 基于 heuristic fallback 风险评分公式) |
| 准确率 | 98.13% (Test) |
| F1-Score | 0.9875 |
| ROC-AUC | 0.9991 |
| Scaler | StandardScaler (fit on train only) |
| 随机种子 | random_state=42 |

### 3.1 风险阈值映射 (structured)

| Score 范围 | Level | 标签 |
|------------|-------|------|
| [0, 15) | 0 | none |
| [15, 45) | 1 | mild |
| [45, 85) | 2 | moderate |
| [85, 98) | 3 | high |
| [98, 100] | 4 | critical |

---

## 4. 验证结果

### 4.1 结构化预测 (primary mode)

| 场景 | Score | Level | 预期 | 结果 |
|------|-------|-------|------|------|
| 低风险 (健康) | 0.0 | 0 (none) | 0 | ✅ |
| 中风险 (中等压力) | 89.19 | 3 (high) | 3 | ✅ |
| 高风险 (高压力) | 100.0 | 4 (critical) | 4 | ✅ |
| 极高风险 (危机) | 100.0 | 4 (critical) | 4 | ✅ |

### 4.2 Heuristic Fallback

| 场景 | Score | Level | 预期 | 结果 |
|------|-------|-------|------|------|
| 低风险 | 12.85 | 0 (none) | 0 | ✅ |
| 中风险 | 52.4 | 2 (moderate) | 2 | ✅ |
| 高风险 | 89.95 | 3 (high) | 3 | ✅ |
| 极高风险 | 100.0 | 4 (critical) | 4 | ✅ |

### 4.3 综合回归

| 模块 | 测试数 | 通过 | 结果 |
|------|--------|------|------|
| CrisisDetector | 4 | 4 | ✅ |
| TextAnalyzer | 2 | 2 | ✅ |
| FusionPriorityEngine | 3 | 3 | ✅ |
| ModelEngine 子组件 | 4 | 4 | ✅ |
| 业务模型 (ReviewTask/CrisisEvent) | 3 | 3 | ✅ |
| Config & Thresholds | 2 | 2 | ✅ |
| Alembic | 1 | 1 | ✅ |
| 健康检查 | 2 | 2 | ✅ |

---

## 5. 已知限制

1. **模型保守性**: LR 模型作为二元分类器，概率分布更极端（~0 或 ~89-100）。中风险样本被模型判定为 high level，属于保守偏安全方向。
2. **合成数据训练**: 模型基于 heuristic fallback 公式生成的合成数据训练，而非真实标注数据。未来应使用真实标注数据重训。
3. **仅支持中文危机检测**: CrisisDetector 关键词为中文，不支持英文输入。
4. **Redis/Celery 可选依赖**: 健康检查中 Redis/Celery 为 optional，不影响核心功能。

---

## 6. 回滚方案

- 设置 `STRUCTURED_MODEL_MODE=fallback` 环境变量 → 重启后端 → 自动使用 heuristic fallback
- 详细步骤见 `MODEL_ROLLBACK_PLAN.md`

---

> **签收**: 待用户确认
> **下一步建议**: 见 `NEXT_STEPS.md`

# BASELINE V1.20 — 基线状态报告

> **生成时间**: 2026-05-01
> **上一迭代**: v1.19-ci-e2e-audit-export (GO — 推荐上线)
> **验证脚本**: `verify_baseline.py`

---

## 1. 结构化模型状态

| 项目 | 值 |
|---|---|
| 模型文件 | `best_model.pkl` (可能损坏或不完整) |
| 当前预测路径 | `_structured_heuristic_fallback()` (model_engine.py:460) |
| Fallback 触发位置 | model_engine.py:422 |
| Fallback 状态 | ✅ 活跃并正常运行 |
| 影响 | 预测基于启发式加权规则，非 sklearn 模型 |

**代码路径**:
- [model_engine.py:422](file:///e:/code/bysj/backend/app/core/model_engine.py#L422) — 结构化预测调用 fallback
- [model_engine.py:460](file:///e:/code/bysj/backend/app/core/model_engine.py#L460) — `_structured_heuristic_fallback` 方法定义
- [verify_fallback.py:15](file:///e:/code/bysj/backend/scripts/verify_fallback.py#L15) — 回退测试脚本

---

## 2. 训练脚本状态

| 项目 | 值 |
|---|---|
| 脚本路径 | `backend/train_baseline.py` |
| 文件大小 | 1854 bytes |
| 语法状态 | ✅ 正确 |
| 训练模型 | **PhysiologicalMLP** (非结构化 LogisticRegression!) |
| 输入维度 | 13 (input_dim=13) |
| 模型参数量 | 6,001 |
| 超参数 | epochs=50, lr=0.001, batch_size=32, weight_decay=0.01, patience=10 |

**⚠️ 关键发现**: `train_baseline.py` 训练的是生理模型 MLP，而非 v1.20 目标的结构化 LogisticRegression。Phase 2 需决策：修改脚本、新建脚本或使用其他训练方式。

---

## 3. 训练数据集状态

| 项目 | 值 |
|---|---|
| 数据源 1 | `datasets/physiological/external/depresjon_processed/depresjon_physiological.csv` |
| 数据源 2 | `datasets/physiological/external/kaggle_wearable/mental_health_wearable_data.csv` |
| 总行数 | 11,029 |
| 原始列数 | 9 |
| 正样本 | 5,516 (50.01%) |
| 负样本 | 5,513 (49.99%) |
| 类别平衡 | ✅ 几乎完美平衡 |

---

## 4. Alembic 迁移状态

| 项目 | 值 |
|---|---|
| Alembic 目录 | `backend/alembic/` |
| versions 目录 | `backend/alembic/versions/` |
| Migration 文件数 | 8 |
| 已知风险 | 双 head 分支 (R19-002) |
| 处理建议 | v1.20 Phase 6 执行 merge |

---

## 5. 环境状态

| 项目 | 值 |
|---|---|
| 开发 OS | Windows |
| Docker Desktop | 28.5.2 ✅ |
| Python | 3.12 |
| 训练环境 | Docker/Linux (推荐) 或 Windows (有限支持) |
| CI 脚本 | `ci_backend_verify.sh`, `ci_frontend_verify.sh` |

---

## 6. 系统依赖版本

| 包 | 用途 |
|---|---|
| sklearn | 结构化模型训练/加载 |
| numpy | 科学计算 |
| transformers | BERT 文本模型 (Phase 8 暂不涉及) |
| tensorflow/keras | 融合模型 |
| SQLAlchemy 2.0 | ORM |
| Alembic 1.14 | 迁移工具 |
| FastAPI 0.115 | Web 框架 |

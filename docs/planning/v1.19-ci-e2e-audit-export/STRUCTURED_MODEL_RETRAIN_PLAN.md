# 结构化模型重训预研 — v1.19-ci-e2e-audit-export

> **执行时间**: 2026-05-01  
> **对应任务**: Phase 7 (Task 7.1-7.2)

---

## 1. 训练脚本

| 项目 | 状态 | 位置 |
|---|---|---|
| train_baseline.py | ✅ 存在 | `backend/train_baseline.py` |
| 依赖导入 | ✅ 完整 | data_loader, data_cleaner, feature_engineering, scaler, data_split, model, trainer, loss |
| 数据加载方式 | ✅ 函数式 | merge_datasets() 通过参数传递 DataFrame |

---

## 2. 训练数据

| 数据源 | 位置 | 状态 |
|---|---|---|
| `student_depression_dataset.csv` | `datasets/structured/` | ✅ |
| `student_mental_health.csv` | `datasets/structured/` | ✅ |
| `enhanced_structured_features.csv` | `datasets/structured/` | ✅ |
| `depresjon_physiological.csv` | `datasets/physiological/external/depresjon_processed/` | ✅ |
| `combined_data.csv` | `datasets/combined/` | ✅ |

---

## 3. 环境依赖

| 依赖 | 版本 | 状态 |
|---|---|---|
| sklearn | 1.7.2 | ✅ |
| numpy | (sklearn 依赖) | ✅ |
| pytorch | ⚠️ 待确认 | — |

---

## 4. Artifact 输出

| 产物 | 说明 |
|---|---|
| 重训后的 scaler | `models/structured/scaler.pkl` |
| 重训后的模型 | `models/structured/physiological_model.pth` |
| 重训后的模型 (ONNX) | `models/structured/physiological_model.onnx` |

---

## 5. 重训建议

1. **直接可执行**: train_baseline.py 可独立运行，不依赖 FastAPI 启动
2. **数据预处理链完整**: merge → clean → engineer → scale → split
3. **建议执行环境**: Docker/Linux（PyTorch onnx 导出更稳定）

---

## 6. 结论

结构化模型重训**技术上可行**。训练脚本、数据、依赖链路完整。建议作为 v1.20 `model-retraining` 专项执行。

---

> **文档版本**: v1.0  
> **最后更新**: 2026-05-01

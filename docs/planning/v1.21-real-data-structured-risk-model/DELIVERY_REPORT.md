# v1.21 交付报告 (DELIVERY_REPORT)

> **日期**: 2026-05-01
> **迭代**: v1.21-real-data-structured-risk-model
> **状态**: Conditional Go ✅

---

## 一、执行总结

v1.21 从"合成数据可用模型"向"真实数据验证模型"迈出了第一步。核心发现：

> **真实世界中的抑郁预测远比合成数据场景困难。** 基础人口学/行为特征与抑郁诊断的相关性接近于零。

---

## 二、Phase 完成情况

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 1 | 数据资产审计 | ✅ 完成 |
| Phase 2 | 标签定义与数据集构建 | ✅ 完成 |
| Phase 3 | 真实数据二分类模型训练 | ✅ 完成 (Conditional Go) |
| Phase 4 | 五级风险模型训练 | ✅ 完成 (No-Go for standalone) |
| Phase 5 | 模型选择、校准与部署集成 | ✅ 完成 |
| Phase 6 | 解释性与监控基线 | ✅ 完成 |
| Phase 7 | 回归测试与交付 | ✅ 完成 |

---

## 三、交付物清单

| 交付物 | 文件 | 状态 |
|--------|------|------|
| 数据审计报告 | `DATA_AUDIT_REPORT.md` | ✅ |
| 标签定义 | `LABEL_DEFINITION.md` | ✅ |
| 二分类模型报告 | `REAL_DATA_BINARY_MODEL_REPORT.md` | ✅ |
| 五级风险报告 | `MULTICLASS_RISK_MODEL_REPORT.md` | ✅ |
| 模型选择报告 | `MODEL_SELECTION_REPORT.md` | ✅ |
| 模型校准报告 | `MODEL_CALIBRATION_REPORT.md` | ✅ |
| 模型解释性报告 | `MODEL_EXPLAINABILITY_REPORT.md` | ✅ |
| 监控基线报告 | `MODEL_MONITORING_BASELINE.md` | ✅ |
| 二分类训练脚本 | `backend/train_structured_v1.21_binary.py` | ✅ |
| 五级分类训练脚本 | `backend/train_structured_v1.21_multiclass.py` | ✅ |
| 模型 Artifacts | `backend/models/artifacts/structured_v1.21/` (11 files) | ✅ |
| 模型注册表更新 | `backend/app/core/model_registry.py` | ✅ |

---

## 四、模型部署状态

| 模型 | 状态 | 配置 |
|------|------|------|
| v1.20 Synthetic LR | ✅ 默认活跃 | `STRUCTURED_MODEL_VERSION=v1.20_synthetic_lr` |
| v1.21 Real Binary LR | ⚠️ 实验性 | `STRUCTURED_MODEL_VERSION=v1.21_real_binary_lr` |
| v1.21 Real Binary RF | ⚠️ 实验性 | 可选 |
| v1.21 Multiclass LR | ❌ 禁用 | `enabled=False` |
| v1.21 Multiclass RF | ❌ 禁用 | `enabled=False` |

---

## 五、关键指标总结

| 指标 | v1.20 Synth LR | v1.21 Real LR |
|------|---------------|--------------|
| F1 | 0.9875 | **0.6000** |
| Recall | ~0.99 | **0.9130** |
| ROC-AUC | 0.9991 | **0.9401** |
| 数据 | 10,000 合成 | 1,000 真实 |

---

## 六、Go / No-Go 判定

**Conditional Go** — 满足以下所有条件：

1. ✅ 真实模型训练完成
2. ✅ 指标分析清晰（低于目标但有充分解释）
3. ✅ v1.20 默认模型不受影响
4. ✅ 真实模型作为实验 artifact 保留
5. ✅ v1.20 fallback 和回滚能力未退化
6. ✅ 模型注册表正确更新

---

## 七、回归测试结果

| 测试项 | 结果 |
|--------|------|
| v1.20 artifact 完整性 | ✅ 5/5 文件存在 |
| v1.21 artifact 完整性 | ✅ 11/11 文件存在 |
| v1.20 model 可加载 | ✅ 成功 |
| v1.21 binary LR 可加载 | ✅ 成功 |
| v1.21 binary RF 可加载 | ✅ 成功 |
| v1.21 multiclass LR 可加载 | ✅ 成功 |
| v1.20 推理可用 | ✅ 通过 |
| v1.21 推理可用 | ✅ 通过 |
| Model Registry 完整性 | ✅ 27 条目，多分类已禁用 |

---

## 八、经验教训

1. **合成数据的高指标是虚假的**：v1.20 合成模型之所以 F1=0.99，是因为学到的就是它自己的标签规则
2. **基础特征与抑郁几乎零相关**：pressure (r=0.007), sleep (r=-0.058), social (r=-0.039) — 仅凭这些无法预测抑郁
3. **Anxiety 是最强预测因子**：LR 系数 +1.30，RF 重要性 0.23 — 远高于其他特征
4. **1,000 样本不足以训练五级模型**：每级仅 60-290 样本，准确率仅 13%-32%
5. **数据泄漏防护是正确选择**：即使牺牲了准确率，排除标签构造列的决策是科学的

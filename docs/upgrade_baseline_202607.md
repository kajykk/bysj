# DWS 模型升级基线 (v1.3 → v1.4)

> **冻结时间**: 2026-07-19
> **基线版本**: v1.3 (当前生产模型)
> **备份位置**: `models/artifacts_v1.3_baseline/`
> **用途**: 作为 v1.4 升级前后的对比基准。所有 v1.4 改动必须能与此基线对照证明改进幅度。

---

## 一、模型矩阵基线快照

| 模态 | 模型类型 | 训练样本 | 测试样本 | Accuracy | Precision | Recall | F1 | AUC | 评估口径 | 可信度 |
|---|---|---|---|---|---|---|---|---|---|---|
| **结构化** | CatBoost | 19,530 | 4,186 | 0.8457 | 0.8451 | 0.9017 | **0.8725** | 0.9204 | 严格 70/15/15 划分 | ✅ 可信 |
| **文本** | TF-IDF + LR | 21,104 (80%) | 5,277 (20%) | 0.7872 | 0.7995 | 0.7790 | **0.7891** | 0.8806 | 严格 80/20 划分 random_state=42 | ✅ 可信 |
| **文本** (评估口径错误) | TF-IDF + LR | — | 7,731 (整集) | 0.9739 | 0.9574 | 0.9914 | **0.9741** ❌ | — | **训练集泄露** | ❌ 虚高 |
| **文本** (评估口径错误) | TF-IDF + LR | — | 1,547 | 0.9677 | 0.9487 | 0.9883 | **0.9681** ❌ | 0.9956 | 与训练 test_split 重叠 | ❌ 虚高 |
| **生理** (原始) | PyTorch MLP (64/32/16) | 719 | 139 | 0.6600 | 0.6091 | 0.8933 | **0.7243** | — | 严格 70/15/15 | ⚠️ 样本过少 |
| **生理** (优化版, 生产) | PyTorch MLP (128/64/32/16+BN) | 719 | 139 | 0.8993 | 0.9318 | 0.7885 | **0.8542** | 0.9653 | 严格 70/15/15 | ⚠️ 样本过少 |
| **融合** (生产) | 规则加权 0.55/0.30/0.15 | — | 4 (手写) | 1.0000 | 1.0000 | 1.0000 | **1.0000** | — | 4 条硬编码场景 | ❌ 无统计意义 |

---

## 二、三个文本 F1 数字根因（已查清）

### F1 = 0.7891 ✅ 真实泛化性能
- **来源**: `models/artifacts/text_depression_classifier/metrics.json` + `training_report.md`
- **数据**: Reddit (7,731) + Twitter (~18,650) 合并 = 26,381，去重去噪后 21,104 + 5,277 train/test
- **方法**: `train_test_split(test_size=0.2, random_state=42, stratify=y)` 后真实评估
- **结论**: 这是当前生产模型的真实能力

### F1 = 0.9741 ❌ 数据泄露虚高
- **来源**: `reports/performance/model_performance_report.md` 第 93 行
- **数据**: Reddit 单数据集 7,731 条全部样本
- **方法**: `scripts/ml_training/evaluate_models.py:85` 调用 `train_test_split(random_state=42)` 后取 `X_test`
- **根因**: 训练时也是 `random_state=42` 划分 Reddit，所以这里的 "test" 与训练时 test 完全重叠；进一步看 samples=7731 说明**根本没划分，整集当测试** → 严重过拟合评估
- **结论**: 必须废弃，重生成报告

### F1 = 0.9681 ❌ 同样数据泄露
- **来源**: `model_assessment/assessment_summary.md` 第 18-20 行
- **数据**: Reddit 单数据集，test 1,547 样本
- **方法**: 与训练时相同 random_state 划分 → test split 重叠
- **结论**: 必须废弃

---

## 三、CV 与稳定性基线（仅结构化模型）

来自 `reports/thesis/第4章_实验设计与结果分析.md` 表4-8：

| 指标 | 均值 | 标准差 |
|---|---|---|
| Accuracy | 0.8458 | 0.0030 |
| Precision | 0.8570 | 0.0039 |
| Recall | 0.8842 | 0.0027 |
| F1 | 0.8704 | 0.0024 |
| ROC AUC | 0.9193 | 0.0016 |

学习曲线泛化差距：0.0312（< 0.1 阈值，无明显过拟合）

---

## 四、推理延迟基线（端到端）

来自 `reports/performance/model_performance_report.md`：

| 模型 | avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) |
|---|---|---|---|---|---|
| 结构化 | 12.86 | 12.42 | 16.42 | 20.13 | 133.03 |
| 文本 | 1.87 | 1.54 | 3.53 | 4.21 | 76.81 |
| 生理 | 0.01 | 0.01 | 0.03 | 0.03 | 0.03 |
| 融合 | 19.57 | 14.90 | 37.21 | 37.21 | 37.21 |

**SLA 基线**: 融合延迟 ≤ 200ms ✅ 达标

---

## 五、训练环境基线

| 维度 | 当前状态 |
|---|---|
| Python | 3.12.0 |
| 操作系统 | Windows 11 (10.0.26200) |
| GPU | NVIDIA RTX 3050 Laptop, **4GB 显存** |
| NVIDIA 驱动 | 572.70 (支持 CUDA 12.8) |
| torch | 2.11.0+cpu (venv 内, **无 CUDA**) |
| transformers | 5.5.0 |
| scikit-learn | 1.7.2 (注意: README 宣称 1.8.0, 实际 1.7.2) |
| catboost | 1.2.10 |

**v1.4 升级前置依赖**: 需安装 `torch+CUDA` (cu128) 才能做 BERT 微调。CPU torch 仅能推理不能训练 BERT。

---

## 六、关键数据资产现状

| 数据集 | 路径 | 样本量 | 当前用途 | v1.4 计划用途 |
|---|---|---|---|---|
| Student Depression | `datasets/Student Depression Dataset.csv` | 27,901 | 结构化训练 ✅ | 保持不变 |
| Reddit cleaned | `datasets/text/depression_dataset_reddit_cleaned.csv` | 7,731 | 文本训练（泄露评估） | 合并到 v2 corpus |
| Twitter | `datasets/text/mental_health_twitter.csv` | 23,095 | 文本训练（未充分利用） | 合并到 v2 corpus |
| Combined | `datasets/combined/combined_data.csv` | 94,024 | **未使用** | 合并到 v2 corpus |
| depresjon (真实抑郁患者) | `datasets/physiological/external/depresjon_processed/` | 1,029 | **未使用** ⚠️ | 生理 v2 corpus 主源 |
| kaggle_wearable | `datasets/physiological/external/kaggle_wearable/` | 10,000 | **未使用** ⚠️ | 生理 v2 corpus 辅源 |
| physiological samples | `datasets/physiological/samples.json` | **4 (手写)** | 生理训练（错误） | 废弃 |
| DAIC-WOZ (三模态) | 需下载 | ~189 session | 无 | 融合真实评估 |

**核心浪费**: depresjon (1029 真实抑郁患者) 和 combined_data (94024 文本) 完全未被使用。

---

## 七、v1.4 升级目标

| 模态 | v1.3 基线 F1 | v1.4 目标 F1 | 关键改进 |
|---|---|---|---|
| 结构化 | 0.8725 | 保持 | 不动 |
| 文本 (TF-IDF+LR) | 0.7891 | **0.90+** | 用 100K corpus 重训 |
| 文本 (BERT 对比) | — | 0.93+ (期望) | bert-base 微调 |
| 生理 | 0.8542 (139 样本) | 0.88+ (1K+ 样本) | 用 depresjon+kaggle 真实数据 |
| 融合 | 1.0 (4 手写) | 真实消融对比 | DAIC-WOZ 真实评估 |

---

## 八、回滚策略

若 v1.4 训练失败/指标劣化，回滚步骤：

1. 模型回滚: `rm -rf models/artifacts && cp -r models/artifacts_v1.3_baseline models/artifacts`
2. 代码回滚: `git checkout <commit-before-v1.4> -- backend/ scripts/`
3. 验证: 运行 `backend/tests/unit/test_physiological_validation.py` 确认旧模型加载正常

**git 标签建议**: 升级前打 `git tag v1.3-baseline`

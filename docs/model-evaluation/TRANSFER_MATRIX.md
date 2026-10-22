# 外部迁移评估矩阵（G2 · ROUND_27）

> **一句话结论：仓内目前没有任何「真外迁」单元可评估。**
> 3 个模态模型 × 6 个数据集的 18 个组合里：**0 个可评估（真外迁）**、
> **2 个部分可评估（降级、非公平基准）**、**16 个 N/A**（特征不相交或标签泄漏）。
> 这不是「本轮没做完」，而是 G2 的**第一个实测结论**：下一步必须先补外部数据，
> 否则任何「跨数据集泛化」的数字都站不住。
>
> 样本量都在各节第一行；所有数字都附复跑命令。

## 一、总表

模型三件（均不重训、不改推理逻辑，只用现有 artifact）：

- **P** = `physiological_optimized`（13 特征，MLP）
- **S** = `structured_v1.20`（14 特征，sklearn）
- **T** = `text_improved_bilingual`（TF-IDF + LR）

| 数据集 | P（生理） | S（结构化） | T（文本） |
|---|---|---|---|
| `depresjon_physiological.csv`（1029） | **域内**（ROUND_26 已评估，非外迁） | N/A·特征不相交 | N/A·无文本列 |
| `kaggle_wearable`（10000） | **部分可评估（降级）** §2.2 | N/A·特征不相交 | N/A·无文本列 |
| `PHQ-9_Dataset_5th Edition.csv`（682） | N/A·特征不相交 | **N/A·标签泄漏** §2.1 | N/A·无文本列 |
| `ood_test_set_v2.csv`（5075） | N/A·特征不相交 | N/A·特征不相交 | **N/A·泄漏**（original/mmpsy）+ **部分可评估（域内压力测试）** §2.3 |
| `actverse/acttrust`（原始 actigraphy） | **N/A·特征不相交** | N/A·特征不相交 | N/A·无文本列 |
| `mmpsy`（1275 用户） | N/A·特征不相交 | N/A·缺 14 列 | N/A·标签泄漏（派生语料参与训练） |

## 二、逐格依据

### 2.1 结构化 × PHQ-9：**N/A · 标签泄漏**（本轮最重要的发现）

提示词前置判断是「仅 ~5/14 重叠 ⇒ 部分可评估」。**实测推翻了这个判断**：

| 证据 | 读数 |
|---|---|
| `PHQ_Total` 逐值分布 | `aligned_features.csv`（S 的训练母表，28,552 行）与 `PHQ-9_Dataset_5th Edition.csv`（682 行）**完全相同**：0:43, 1:40, 2:44, 3:27, 4:52, 5:31, 6:36, 7:35, 8:20, 9:33, 10:29, 11:20 … |
| 标签口径 | `aligned_features.label_binary` 恰为 `phq9_total >= 10`（阳性最小 10、阴性最大 9），与 PHQ_Severity 的 Moderate+ 一致 |
| 行数关系 | 28,552 / 682 ≈ 41.9 ⇒ 训练母表是这 682 行的复制/增强 |
| 脚本层面 | `grep -rn "PHQ-9_Dataset" --include="*.py"` **零命中**：它不是被「读取」的外部数据，而是被**合成进**训练母表 |

⇒ **PHQ-9 不是外部数据，是结构化模型的训练标签来源**。在它上面评估 = 在训练集上评估。
复跑核查：

```bash
cd backend
.venv/Scripts/python.exe - <<'PY'
import pandas as pd
a = pd.read_csv("../data/external/aligned_features.csv", encoding="utf-8-sig")
p = pd.read_csv("../datasets/PHQ-9_Dataset_5th Edition.csv", encoding="utf-8-sig")
print(a.phq9_total.value_counts().sort_index().head(12).to_dict())
print(p.PHQ_Total.value_counts().sort_index().head(12).to_dict())   # 逐值相同
print(a[a.label_binary==1].phq9_total.min(), a[a.label_binary==0].phq9_total.max())  # 10 / 9
PY
```

### 2.2 P × Kaggle Wearable：**部分可评估（降级）**

**n = 10,000**（全量，不抽样）。

- 特征映射（3/13 真实）：
  `Sleep_Duration_Hours → sleep_hours`、`Heart_Rate_BPM → heart_rate`、
  `Physical_Activity_Steps → steps`；
  缺 4 列（`sleep_quality`/`exercise_minutes`/`systolic_bp`/`diastolic_bp`）
  **按生产默认值填充**（`predict.py::_predict_physiological_sync` 的 raw_data：
  5 / 30 / 120 / 80），随后仍走 artifact cleaner 的 winsor 边界，不丢任何行。
- 标签：`Mental_Health_Condition`（0/1）。
- **清洗陷阱（实测）**：若直接把 7 列交给 `DataCleaner.transform`，因每行缺 4/7=57% > 30%
  会被 `drop_high_missing_samples` **全部丢光**；故必须先按生产默认值补齐再 transform。

| 指标 | 点估计 | 95% CI（bootstrap B=10000, seed=42） |
|---|---|---|
| Accuracy | 0.4801 | [0.4701, 0.4898] |
| Precision | 0.4930 | [0.4756, 0.5108] |
| Recall | 0.2883 | [0.2762, 0.3008] |
| F1 | 0.3639 | [0.3507, 0.3772] |
| **ROC AUC** | **0.5120** | **[0.5006, 0.5233]** |

混淆矩阵：TP=1487 / FP=1529 / FN=3670 / TN=3314。

**怎么读**：AUC 0.512 的 95% CI 覆盖 0.5 ⇒ **与随机猜测不可区分**。
这既是「跨设备/跨协议迁移失败」的证据，也说明该模型高度依赖那 4 个被填成常量的特征。
⚠️ 两重限定：(a) 4/7 原始特征是常量 ⇒ 这是**下界**、非公平基准；
(b) v2 的训练脚本从未入库，**无法确证 Kaggle 未参与训练**（ROUND_26 已证 artifact
与仓内三份数据都不匹配，训练数据是第四份）。因此本格只能作**压力测试**，不作外迁结论。

复跑：

```bash
cd backend
.venv/Scripts/python.exe scripts/modeling/eval/v1_29/02_transfer_eval.py --unit physio_kaggle
.venv/Scripts/python.exe scripts/modeling/eval/v1_29/02_transfer_eval.py --unit physio_kaggle --report-only
```

### 2.3 T × OOD：**N/A（original/mmpsy）+ 部分可评估（eda strict，域内压力测试）**

**n = 2,523**（`S2_ood_strict`：与训练语料**精确**去重后的子集）。

污染结构（复用 `v1_27/02_ood_validate_bilingual.py` 的口径，本轮复算一致）：

| 子集 | 行数 | 在训练语料 | 判定 |
|---|---|---|---|
| `original` | 1,275 | **1,275**（`in_v1_original`） | N/A · 标签泄漏 |
| `mmpsy_augmented` | 1,175 | **1,175**（`in_train_augmented`） | N/A · 标签泄漏 |
| `eda` | 2,550 | 27 在 v1 original；**2,523 精确不重叠** | 部分可评估（兄弟泄漏，域内） |

| 指标（eda strict） | 点估计 | 95% CI（B=10000, seed=42） |
|---|---|---|
| Accuracy | 0.9945 | [0.9913, 0.9972] |
| Precision | 1.0000 | [1.0000, 1.0000] |
| Recall | 0.9727 | [0.9574, 0.9862] |
| F1 | 0.9862 | [0.9783, 0.9930] |
| ROC AUC | 0.9986 | [0.9956, 0.99999] |

**怎么读**：F1 0.986 / AUC 0.9986 **不能**读作「文本模型泛化好」。eda 子集是
original 的 EDA 改写（同义替换/增删词），与训练语料只差表面形式 ⇒ 高指标本身
就是**兄弟泄漏的证据**（对照：真 groupwise 泛化口径是 F1 0.5864，见
`docs/EVALUATION_TRUST_SUMMARY.md`）。本格只作**域内压力测试**。

复跑：

```bash
cd backend
.venv/Scripts/python.exe scripts/modeling/eval/v1_29/02_transfer_eval.py --unit text_ood
.venv/Scripts/python.exe scripts/modeling/eval/v1_29/02_transfer_eval.py --unit text_ood --report-only
```

### 2.4 其余 N/A 的依据

| 单元 | 依据 |
|---|---|
| P × PHQ-9 / ood / actverse / mmpsy | PHQ-9、ood、mmpsy 都没有生理时间序列/体征列；actverse 是**原始 actigraphy**（逐分钟活动计数），与 `sleep_hours/heart_rate/systolic_bp/...` 13 个临床/生活派生特征**不相交**——要对接必须重做特征工程并重训（提示词明确划到 G2 之外） |
| S × depresjon / kaggle / ood / actverse / mmpsy | 这 5 个数据集都没有 14 列学生问卷字段（`cgpa`/`study_year`/`social_support`/`family_history`/`anxiety`/`panic_attack`/`treatment_seeking`…） |
| T × depresjon / kaggle / PHQ-9 / actverse | 无中文/英文自由文本列（PHQ-9 只有条目选项、actverse 只有活动计数） |
| T × mmpsy | 派生语料 v1/v2 已参与训练（`chinese_depression_corpus_v1.csv` 是 `v1_27/04` 的训练输入）⇒ 标签泄漏 |

## 三、为什么「0 个真外迁」是可接受的结论

1. **G2 的任务是「验证外部迁移」，第一步必然是「盘清有没有外部数据」**——
   本轮把这个盘清了：仓内 6 份数据里，4 份与训练同源（PHQ-9 是标签母体、mmpsy/中文语料是
   文本训练母体、depresjon 是生理评估母体），1 份特征不相交（actverse），1 份未确证未参与训练
   （kaggle）。
2. **硬凑映射会制造伪数字**：例如把 `Sleep Quality`（1-4 序数）硬当 `sleep_duration`（小时），
   或把 `Mood_Rating`（1-10）当 `sleep_quality`，能算出一个「看起来像外迁」的 F1——
   但那只是给模型喂噪声。本矩阵拒绝这样做（提示词纪律：N/A 必须给依据，不得硬凑）。
3. **两个降级单元的价值**：它们给出了「如果硬要用」的**下界读数**——
   P × Kaggle 的 AUC 0.512 明确告诉决策者：这个生理模型**不能**直接用于可穿戴设备数据；
   T × OOD(strict) 的 F1 0.986 明确告诉读者：OOD 报告里的高分是泄漏，不是泛化。

## 四、G2 的输入清单（下一轮可直接开工）

| 需要什么 | 为什么 | 候选来源 |
|---|---|---|
| **真·生理外部集**（含 sleep_quality / BP 等 7 列） | 目前只有 kaggle 的 3 列能映射 | `datasets/physiological/external/` 下的其他公开集（需先登记 `DATASETS.md`） |
| **结构化外部集**（≥10/14 列学生问卷） | PHQ-9 已证是训练母体 | 高校心理中心合作数据（`manifest.json` 的 next_steps 已列） |
| **中文文本外部集**（与 mmpsy/v1/v2 不同源） | 现有全部同源 | 新采集/其他公开中文心理语料（需许可核查） |
| 上述三者的**许可证据** | `DATASETS.md` §7：许可未知的不得出对外数字 | — |

## 五、产物与复算

| 单元 | 逐样本 | 校验和 | 指标 JSON | 人读报告 |
|---|---|---|---|---|
| `text_ood` | `backend/models/artifacts/eval_transfer/transfer_text_ood_predictions.csv`（2,523 行） | `.csv.sha256` | `docs/model-evaluation/transfer_text_ood_eval.json` | `transfer_text_ood_report.md` |
| `physio_kaggle` | `.../transfer_physio_kaggle_predictions.csv`（10,000 行） | `.csv.sha256` | `docs/model-evaluation/transfer_physio_kaggle_eval.json` | `transfer_physio_kaggle_report.md` |

口径与 ROUND_27 A 摊一致：csv 存 `.17g`（float64 往返）、指标与 CI 按**落盘行序**计算、
`--report-only` 同时重写 JSON + 报告。**验收**：对已提交的 csv 跑 `--report-only`，
重写产物必须与提交版逐字节相等。

**加速与对拍**：n=10,000 × B=10,000 的纯 Python AUC 循环 >5 分钟（实测被系统终止），
故 02 脚本用 `scipy.rankdata` 的向量化平均秩，并保持 `rng.randint` 的调用序列与 01 完全一致；
`--verify-fast` 在 text_ood 上与 01 逐位对拍：**max CI diff = 0.000e+00（PASS）**。

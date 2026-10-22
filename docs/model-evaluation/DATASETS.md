# 外部数据集登记表（G2 的启动输入）

> 目的：让 G2（外部迁移验证）启动时**不必再查许可与来源**。
> 本表 2026-10-23 逐项实读登记；**本轮不跑任何外部评估**（那是 G2）。
> 未在仓内留下许可证据的条目，一律标「许可未知」，不代填。

## 0. 速览

| 数据集 | 用途 | 许可 | 是否已用于训练 | G2 可用性 |
|---|---|---|---|---|
| Depresjon（生理） | 生理模型训练/评估 | 见 §1 | 是（当前评估的唯一样本源） | 可用（已在本仓） |
| Kaggle Wearable（生理） | 生理模型训练候选 | 见 §2 | **否**（合并代码存在但训练未用） | 可用（已在本仓） |
| PHQ-9 Dataset 5th Edition | 量表级真值 | 见 §3 | 否 | 可用（已在本仓） |
| actverse（acttrust） | 活动记录仪样例 | GPLv3 | 否 | 谨慎（GPL 传染性） |
| MMPsy（多模态心理） | 中文文本/音频 | MIT | 否（仅派生语料参与训练） | 可用 |
| 中文抑郁语料 v1 / v2 | 中文文本训练 | 派生自 MMPsy（MIT） | 是（v2 用于 lite/文本模型） | 可用（须标派生） |

---

## 1. Depresjon（生理信号）

| 字段 | 值 |
|---|---|
| 名称 | Depresjon（processed 版） |
| 仓内路径 | `datasets/physiological/external/depresjon_processed/depresjon_physiological.csv`（1029 行，1,030 含表头）；`depresjon_augmented.csv`（7,203 行，增强版） |
| 来源 | 仓内文件头标注 `source=depresjon`；原始数据来自 Depresjon 公开数据集（Dartmouth 活动记录仪队列），**仓内无原始 LICENSE 文件** |
| 版本 / 日期 | 文件 mtime 2026-04-27；无显式版本号；行数与列名（steps/heart_rate/sleep_hours/sleep_quality/exercise_minutes/systolic_bp/diastolic_bp/depression_label/phq9_score/mean_activity/std_activity/peak_activity/autocorrelation）已在本表登记 |
| 许可 | **未在仓内留下许可证据**（无 LICENSE）。用于研究/论文须回溯源数据集获取条款后再对外发布 |
| 引用要求 | 引用 Depresjon 原始论文（Garcia-Ceja et al., 2018）；仓内代码路径 `app/ml/data_loader.py::load_depresjon_data` |
| 是否已用于训练 | **是**——`physiological`(v1) 与 `physiological_optimized`(v2) 的训练/评估均基于此文件（v2 的原切分不可复现，见 `PHYSIO_V2_EVAL_REPORT.md` §一） |
| 拟用于何种评估 | G2 的「同分布跨采集点」对照；不得再作为「外部」验证集（已参与训练/调参） |
| 纳入日期 | 2026-10-23（本表首次登记） |

## 2. Kaggle Wearable（生理信号）

| 字段 | 值 |
|---|---|
| 名称 | Mental Health Wearable Data（Kaggle） |
| 仓内路径 | `datasets/physiological/external/kaggle_wearable/mental_health_wearable_data.csv`（10,000 行） |
| 来源 | Kaggle 公开数据集；列 `Heart_Rate_BPM / Sleep_Duration_Hours / Physical_Activity_Steps / Mood_Rating / Mental_Health_Condition` |
| 版本 / 日期 | 文件 mtime 2024-10-17；无版本号 |
| 许可 | **未在仓内留下许可证据**（无 LICENSE）；Kaggle 数据集条款须回到原始页面确认 |
| 引用要求 | 引用 Kaggle 数据集页面（当前仓内未记录 slug，须补） |
| 是否已用于训练 | **否**——`app/ml/data_loader.py::merge_datasets` 会合并它，但当前 artifact 的训练分布与合并数据不符（见评估报告 §一） |
| 拟用于何种评估 | G2 的**跨数据集迁移**首选：同特征域（心率/睡眠/步数）、不同采集协议，且未参与训练 |
| 纳入日期 | 2026-10-23 |

## 3. PHQ-9 Dataset 5th Edition（量表）

| 字段 | 值 |
|---|---|
| 名称 | PHQ-9 Dataset（5th Edition） |
| 仓内路径 | `datasets/PHQ-9_Dataset_5th Edition.csv`（682 数据行，683 含表头） |
| 来源 | 公开问卷数据集（仓内无来源 URL/作者记录）；列含 9 个 PHQ 条目原文 + `PHQ_Total` + `PHQ_Severity` + 3 个生活压力项 |
| 版本 / 日期 | 文件名即「5th Edition」；文件无显式日期 |
| 许可 | **未知**（无 LICENSE、无 README） |
| 引用要求 | 须补齐来源与引用（当前只在文件名层面可追溯）；9 条目为 PHQ-9 标准文本（Kroenke et al., 2001） |
| 是否已用于训练 | **否**（仅作量表口径参考；`PHQ-9_Dataset_5th Edition.csv` 未出现在任何训练脚本中） |
| 拟用于何种评估 | G2 的**条目级一致性**检查（模型风险分数 vs PHQ-9 总分/严重度分层）；注意本表**无逐条目标注以外的文本列**，不能做文本-量表配对 |
| 纳入日期 | 2026-10-23 |

## 4. actverse / acttrust（活动记录仪）

| 字段 | 值 |
|---|---|
| 名称 | actverse（R 包）内置 `acttrust` 示例数据 |
| 仓内路径 | `datasets/external/physiological/actverse/`（整包 vendored，含 `data-raw/acttrust.csv`、`data/acttrust.rda`、`CITATION.cff`、`LICENSE.md`） |
| 来源 | GitHub `danielvartan/actverse`（R 包，处理/可视化 actigraphy 数据）；`CITATION.cff` 记 v0.2.0，作者 Vartanian, Matias, Serrano, Benedito-Silva |
| 版本 / 日期 | 0.2.0（`CITATION.cff`）；包内无独立日期 |
| 许可 | **GPL-3.0**（`LICENSE.md` 全文为 GNU GPL v3） |
| 引用要求 | 引用 `actverse: An R package for actigraphy data analysis`（`CITATION.cff` 的 preferred-citation） |
| 是否已用于训练 | **否**（仅 vendored 参考实现，未进入任何数据管线） |
| 拟用于何种评估 | **不建议直接用于 G2 评估**：GPL-3.0 的传染性会波及派生数据/代码的分发；如确需使用，只能作「方法对照」（读取其预处理逻辑），不复制数据进交付物 |
| 纳入日期 | 2026-10-23 |

## 5. MMPsy（多模态心理数据）

| 字段 | 值 |
|---|---|
| 名称 | Multi-Modal Psychology Data（MMPsy） |
| 仓内路径 | `data/external/mmpsy-data/`（`LICENSE`/`README.md`/`data/`/`model/`/`data_generation.py`） |
| 来源 | 官方数据仓库，对应论文 *Mental-Perceiver: Audio-Textual Multimodal Learning for Mental Health Assessment*（arXiv:2408.12088）；README 记 **1,275 名真实学生**的量表分数、访谈音频与文本 |
| 版本 / 日期 | 无显式版本；LICENSE 记 `Copyright (c) 2024 shuyeit` |
| 许可 | **MIT**（`data/external/mmpsy-data/LICENSE` 全文） |
| 引用要求 | 引用 Mental-Perceiver 论文（arXiv:2408.12088）+ 该仓库 |
| 是否已用于训练 | **派生语料参与训练**（见 §6）；原始多模态数据本身未直接进训练 |
| 拟用于何种评估 | G2 的**中文文本/多模态迁移**：可作为「跨语料」对照，但须按 `user_id` 分组切分（`v1_23_external/split_metadata.json` 的随机划分有分组泄漏嫌疑，已在 `docs/ML_LEAKAGE_AUDIT.md` 登记） |
| 纳入日期 | 2026-10-23 |

## 6. 中文抑郁语料 v1 / v2（MMPsy 派生）

| 字段 | 值 |
|---|---|
| 名称 | 中文抑郁语料 v1 / v2（含 clean 版与快照） |
| 仓内路径 | `data/external/chinese_depression_corpus_v1.csv`（8,511 行）、`..._v1_snapshot_8377.csv`、`..._v2.csv`（15,244 行）、`..._v2_clean.csv`；`mmpsy_augmented.csv`（增强）、`ood_test_set_v2.csv`（分布外测试集） |
| 来源 | **MMPsy（§5）的派生**：列结构与 MMPsy 完全一致（`user_id/phq9_*/gad7_*/audio_*/text/augmentation/source_idx`），`source_idx` 可回溯源样本、`augmentation` 列标记合成行 |
| 版本 / 日期 | v1 mtime 2026-07-23、v2 mtime 2026-07-24、v2_clean 2026-07-27；行数即版本 |
| 许可 | **继承 MMPsy 的 MIT**（派生数据）；但**派生文件本身无 LICENSE**，对外分发须同时附 §5 的 MIT 声明与派生说明 |
| 引用要求 | 引用 Mental-Perceiver（arXiv:2408.12088）+ 说明「由 MMPsy 派生、含 `augmentation` 标记的合成样本」 |
| 是否已用于训练 | **是**（v2/clean 用于 lite 与文本侧训练；`mmpsy_augmented` 为增强语料） |
| 拟用于何种评估 | G2 的**中文跨域泛化**必须以 `user_id` 分组切分（文本模态 groupwise F1 = 0.5864 是当前可引用的泛化口径，见 `docs/EVALUATION_TRUST_SUMMARY.md`）；**不得**用 `v1_23_external` 的随机划分再报一次「外部」指标 |
| 纳入日期 | 2026-10-23 |

---

## 7. 登记口径说明

1. **「是否已用于训练」只认仓内代码证据**（训练脚本/管线实际读取），不认文件名或目录位置。
2. **「许可」只认仓内 LICENSE/CITATION 原文**；没有就写「未知/未在仓内留下证据」——G2 启动前必须补齐，不得用「公开数据集」代替许可条款。
3. **`data/external/` 被 `.gitignore` 排除**（112MB+），clone 后需按 `data/README.md` 单独获取；本表登记的是**本机实测形态**（行数以实测为准）。
4. G2 启动时的最小检查清单：每个拟用数据集必须满足「许可已核实 + 未参与训练（或已按分组隔离）+ 引用要求已满足」三条，缺一不得出对外数字。

# ML 评估入口泄漏 / 选择偏差审计清单（P2 新阶段 · 方向 B）

> 执行日期：2026-10-19｜基准 HEAD：`f1c4b4e`（与 origin/main 同 sha，工作树 `git diff`=0）
> 工具：`backend/tests/tools/leakage_audit_scan.py`（AST 扫描）、
> `backend/tests/tools/leakage_delta_probe.py`（口径对照 + 目标泄漏检测）
> 闸门：`backend/tests/test_p2_38_leakage_audit_guard.py`（8 条）
> 变异：`backend/tests/tools/mutate_p2_38_round14.py`（4 个，红→还原绿）
> 对外摘要：[评估可信度 · 一页摘要](EVALUATION_TRUST_SUMMARY.md)｜对外概览：[README 60 秒概览](../README.md#60-秒概览)

## 一、为什么做这次审计（三重印证，不是自说自话）

| 来源 | 结论 |
|---|---|
| 本项目 P2-1（2026-10-05） | 同一批数据：groupwise CV F1 **0.5864** vs textwise **0.9964**，差 0.41 |
| `2607.02920` | random-split 是系统性高估源 |
| `2610.06465` | best-of-N 调参是系统性高估源 |

三者同向指向：**「随机划分 + 逐层挑优」会让评估指标失去意义**。
因此方向 B 的目标是：把全仓 ML 评估入口盘清楚，凡属此类的统一识别、记账，并做成可复用守卫。

**边界声明**：本轮**不改动任何现役预测主路径，也不改动任何既有 ML 脚本的评估口径**。
只做检测与记账——因为改口径会连带推翻历史读数，必须先有清单再谈整改。

## 二、方法

1. **AST 扫描**（不是文本匹配）：遍历 **git 跟踪的** `.py`（`git ls-files`），
   提取 `ast.Call` 中属于
   `train_test_split / KFold / GroupKFold / StratifiedKFold / StratifiedGroupKFold /
   ShuffleSplit / GroupShuffleSplit / LeaveOneGroupOut / LeavePGroupsOut /
   TimeSeriesSplit / cross_val_score / cross_validate / cross_val_predict` 的调用点，
   连带提取其 keyword 实参名。
   *用 AST 的理由：文本扫描会命中扫描器自己的 docstring 与字符串，产出假证据。*
2. **排除范围**：`tests/`（测试代码不是评估口径）、
   `datasets/external/`（第三方仓库副本，含 `archive/`，不属本仓自研口径）。
   > 补记：`datasets/` 下的 581 个 py **全部未入库**，改用 `git ls-files` 后本就
   > 不会被扫到；`external` 排除项保留作双保险，但已不是唯一防线。
3. **工具只做粗排**——每条候选仍需人工核对后才进清单（见 §五的裁定表）。

> ⚠️ **第二处工具缺陷（CI 实锤，比第一处更值得记）**：
> 扫描器初版用 `rglob` 扫**本机工作树**，把 3 个**未入库**的脚本也计入候选，
> 得到 42 文件 / 92 入口；而 CI 的干净 checkout 只有 **39 文件 / 87 入口**
> ⇒ 清单棘轮（`test_scanner_sees_full_inventory`）在 CI 上必红。
> 未入库的三个是：`models/train_tabular_depression.py`、
> `models/train_text_depression_classifier.py`、`scripts/deep_analysis_fix.py`。
> **修正**：扫描源改为 `git ls-files`（只认交付形态），基线改钉 39 / 87，
> 并新增 AST 源码级断言 `test_scanner_sources_from_git_tracked_files`
> 钉住「不得再用 rglob」。这正是「断言必须钉**交付形态下不变的事实**，
> 而不是本机碰巧成立的状态」这条纪律的第四次实锤。

> ⚠️ 过程中发现并修正了一个真实的工具缺陷：扫描器的路径常量
> `parents[2]` 实际指向 `backend/` 而非仓库根，导致根目录 `scripts/`
> （含 `m2_group_cv_eval.py` 等 26 个文件）**整体漏扫**。
> 修正前后：28 条 / 13 文件 → 118 条 / 56 文件（**漏了 4 倍**）。
> 这条本身印证了「判据必须实测、不信转引」的纪律。

## 三、三类问题定义

| 代号 | 问题 | 判据 | 能否靠换 CV 修好 |
|---|---|---|---|
| **L1** | 随机划分不守恒 | 数据存在兄弟/重复结构，却用 `train_test_split`/`StratifiedKFold` 而非按组划分 | ✅ 能（改 groupwise） |
| **L2** | 逐层挑优 / best-of-N 选择偏差 | 在同一验证集上反复选超参/特征组并只报最优 | ⚠️ 部分（需嵌套选择） |
| **L3** | 阈值在评估集上选 | 决策阈值在 test/eval 折上扫描取优 | ✅ 能（阈值须在训练折内定） |
| **L4** | **目标泄漏** | 特征是标签的确定性/近似确定性函数 | ❌ **不能**——换任何 CV 都无效 |

**L4 是本轮最严重的发现**，见 §五。

## 四、全量清单（40 文件 / 88 入口）

区域划分：`A` 生产服务 / `B` v1.27 建模 / `C` v1.23~26 建模 / `D` 后端脚本 / `E` ML 训练 / `F` 历史实验

| 区域 | 文件 | 入口数 | 调用 | 风险标签 |
|---|---|---|---|---|
| A | `backend/app/ml/fusion_ablation.py` | 1 | `StratifiedGroupKFold`×1 | 合规（groups 传 `.split()`，AST 误报已核） |
| A | `backend/app/ml/hyperparameter_tuning.py` | 5 | `best_f1`×5 | L2 |
| A | `backend/app/services/experiment_data.py` | 2 | `train_test_split`×2 | L1 |
| B | `backend/scripts/modeling/v1_27/01_calibrate_lite_lr.py` | 2 | `train_test_split`×2 | L1 |
| B | `backend/scripts/modeling/v1_27/03_groupwise_leakage_free_eval.py` | 2 | `StratifiedGroupKFold`×1, `StratifiedKFold`×1 | 合规（对照臂） |
| B | `backend/scripts/modeling/v1_27/04_retrain_bilingual_text_groupwise.py` | 4 | `StratifiedGroupKFold`×3, `train_test_split`×1 | L1 |
| C | `backend/scripts/modeling/v1_23/01_prepare_external_dataset.py` | 4 | `train_test_split`×4 | L1 |
| C | `backend/scripts/modeling/v1_24/02_validate_mmpsy.py` | 1 | `cross_val_score`×1 | L1+**L4** |
| C | `backend/scripts/modeling/v1_25/02_train_lite_model.py` | 2 | `train_test_split`×1, `StratifiedKFold`×1 | L1 |
| C | `backend/scripts/modeling/v1_25/03_ablation_study.py` | 2 | `StratifiedKFold`×2 | L2 |
| C | `backend/scripts/modeling/v1_26/00_reproduce_baseline.py` | 1 | `train_test_split`×1 | L1 |
| C | `backend/scripts/modeling/v1_26/01_threshold_sweep.py` | 1 | `train_test_split`×1 | L1+L3 |
| D | `backend/scripts/modeling/verify_current_models.py` | 1 | `train_test_split`×1 | L1 |
| E | `scripts/ml_training/data_utils.py` | 2 | `train_test_split`×2 | L1 |
| E | `scripts/ml_training/evaluate_models.py` | 2 | `train_test_split`×2 | L1 |
| E | `scripts/ml_training/train_bilingual_text.py` | 2 | `train_test_split`×2 | L1 |
| E | `scripts/ml_training/train_fusion.py` | 1 | `train_test_split`×1 | L1 |
| E | `scripts/ml_training/train_text.py` | 1 | `train_test_split`×1 | L1 |
| F | `scripts/data_prep/structured_feature_engineering.py` | 5 | `train_test_split`×4, `StratifiedKFold`×1 | L1+L2 |
| F | `scripts/deep_analysis.py` | 4 | `train_test_split`×2, `cross_validate`×1, `StratifiedKFold`×1 | L1 |
| F | `scripts/eval_model.py` | 1 | `best_threshold`×1 | L3 |
| F | `scripts/evaluation/evaluate_model.py` | 2 | `cross_validate`×1, `StratifiedKFold`×1 | L1 |
| F | `scripts/lib/fusion_pipeline.py` | 8 | `StratifiedKFold`×8 | L1 |
| F | `scripts/m1_structured_gbdt.py` | 2 | `StratifiedKFold`×2 | L1 |
| F | `scripts/m2_group_cv_eval.py` | 2 | `GroupKFold`×1, `StratifiedKFold`×1 | 合规（含 group 臂）+ L1 对照 |
| F | `scripts/m2_text_bert.py` | 4 | `StratifiedGroupKFold`×2, `StratifiedKFold`×2 | 合规 + L1 对照 |
| F | `scripts/m2_text_bert_retrain.py` | 1 | `StratifiedGroupKFold`×1 | 合规 |
| F | `scripts/m5_calibration_thresholds.py` | 4 | `StratifiedKFold`×2, `best_threshold`×2 | L1+L3 |
| F | `scripts/multi_model_compare.py` | 2 | `train_test_split`×2 | L1 |
| F | `scripts/optimize_fusion_weights.py` | 2 | `best_f1`×2 | L2+L3 |
| F | `scripts/p2_bert_onnx_quantize.py` | 1 | `StratifiedKFold`×1 | L1 |
| F | `scripts/p2_bert_quantization.py` | 1 | `StratifiedKFold`×1 | L1 |
| F | `scripts/t1_bert_grid.py` | 2 | `best_f1`×2 | L2 |
| F | `scripts/t1_group_cv_tool.py` | 2 | `GroupKFold`×1, `StratifiedKFold`×1 | 合规 + L1 对照 |
| F | `scripts/t1_sentence_embedding_eval.py` | 1 | `GroupKFold`×1 | 合规 |
| F | `scripts/train_and_eval.py` | 2 | `train_test_split`×2 | L1 |
| F | `scripts/train_physiological.py` | 1 | `best_score`×1 | L2 |
| F | `scripts/train_physiological_xgboost.py` | 1 | `best_score`×1 | L2 |
| F | `scripts/train_structured_fallback.py` | 3 | `train_test_split`×1, `best_score`×2 | L1+L2 |
| F | `scripts/train_text_bert.py` | 1 | `train_test_split`×1 | L1 |

**区域汇总**：A 3 文件/8 入口｜B 3/8｜C 6/11｜D 1/1｜E 5/8｜F 22/52｜**合计 40 文件 / 88 入口**

> 口径说明：本清单只含 **git 跟踪（已交付）** 的脚本。初版曾列 42 文件/92 入口，
> 其中 `models/train_tabular_depression.py`、`models/train_text_depression_classifier.py`、
> `scripts/deep_analysis_fix.py` 三个**未入库**，已按交付形态剔除（详见 §二补记）。
> 这三个若将来入库，清单棘轮会红并强制重新审计。

> ROUND_16 补记（2026-10-20 实测扫描：files_touched=40 / total_findings=88）：
> T2 融合消融新增 `backend/app/ml/fusion_ablation.py` 的
> `groupwise_kfold_indices`。扫描器 AST 层只查划分器**构造器** kwargs 中的
> `groups=`，而本实现把 `groups` 传给 `.split()`，并在返回前逐折实测
> 「同组不跨折」（重叠即 raise）⇒ 标签 `group_aware_without_groups` 为
> **AST 层误报**，人工逐条核对后记账为合规入口（已登记守卫基线
> BASELINE_FILES=40 / BASELINE_ENTRIES=88）。

## 五、关键发现（按严重度排序）

### F1（最高）· `stress_level` 是标签的确定性函数 ⇒ 目标泄漏（L4）

`backend/scripts/modeling/v1_24/01_build_mmpsy_features.py`：

```python
def derive_stress(phq9: float) -> float:
    return round(phq9 / 27.0 * 5.0, 4)
```

而审计目标 `phq9_binary` 由 `phq9_score >= 10` 派生（实测：`=1` 的最小分 10，`=0` 的最大分 9）。
⇒ `stress_level` 与标签**一一对应**。实测印证：

- `corr(stress_level, phq9_score)` = **1.0**
- `stress_level` **单特征 AUC = 1.0000**

**后果**：任何把 `stress_level` 作为输入的「模型性能」读数都是同义反复，
包括 `v1_24/02_validate_mmpsy.py:87` 的 `cross_val_score(cv=5)` 3-feature 基线
（含 `stress_level`、`anxiety`、`panic_attack`）。
**这条不能靠换 CV 修复**——必须从特征集里剔除或改用非派生特征。

### F2 · 中文语料的兄弟泄漏（L1）— 本轮独立复现

`chinese_depression_corpus_v1.csv`：8379 行 / `source_idx` 仅 1244 个唯一组，
每组最多 7 个增强变体（`syn_v1~v6`、`synonym_replace`、`backtranslation`）。
随机划分会把同一原始样本的变体分到 train 与 eval ⇒ 记忆泄漏。

实测（生产同款：jieba 分词 TF-IDF + `LogisticRegression(C=1.0, balanced)`，固定阈值 0.3）：

| 口径 | F1 | ROC-AUC |
|---|---|---|
| R 随机（文本级，变体跨 fold） | 0.8860 | 0.9994 |
| G 组级（sibling-aware） | 0.5749 | 0.8421 |
| **Δ = 泄漏虚高** | **+0.3111** | **+0.1573** |

### F3 · mmpsy 结构化特征碰撞（L1，但实测不虚高）

`mmpsy_structured_features.csv`：1275 行去重后仅 780 行唯一特征组合
（218 个重复组、涉及 713 行，占 55.9%；**组内标签一致率 100%**）。

按「特征行碰撞」分组后重跑对照：

| 口径 | F1 | ROC-AUC |
|---|---|---|
| R 随机 | 0.8672 | 0.9996 |
| G 组级（按碰撞分组） | 0.8658 | 0.9996 |
| **Δ** | **+0.0014** | **+0.0000** |

**判读（重要，也是本轮对方向 B 前提的修正）**：
Δ≈0 **不是**因为没泄漏，而是**天花板效应**——该任务用 12 个结构化特征本就
近乎完美可分（AUC 0.9996），真实信号已足够强，模型不依赖记忆副本。
⇒ **「有重复数据」≠「指标虚高」**，必须实测才知道。一刀切判「随机划分=泄漏」是错的。

### F4 · 生产路径 `experiment_data.py`（L1，待定）

`backend/app/services/experiment_data.py:156,174` 在**运行时**对上传数据集做
`train_test_split(random_state=42, shuffle=True, stratify=label)`。
这是**数据准备**而非模型评估，风险取决于上传数据中是否存在重复/变体样本。
当前**无 group 概念** ⇒ 若用户上传含增强变体的数据集，即为 L1 泄漏。

### F5 · 阈值扫描（L3，待核实）

`scripts/m5_calibration_thresholds.py`（`best_threshold`×2）、
`scripts/eval_model.py`（`best_threshold`×1）、
`v1_26/01_threshold_sweep.py`、`optimize_fusion_weights.py`（`best_f1`×2）
存在阈值/权重挑优。**是否已污染评估集尚未逐条核实**——见 §七记账。

## 六、守卫与 CI

| 产物 | 作用 |
|---|---|
| `backend/tests/tools/leakage_audit_scan.py` | AST 扫描全仓划分入口，输出候选 JSON |
| `backend/tests/tools/leakage_delta_probe.py` | 同数据双口径对照 + 目标泄漏检测；`--self-test` 自检 |
| `backend/tests/test_p2_38_leakage_audit_guard.py` | 9 条闸门（G1 探针有效性 / G2 目标泄漏 / G3 反弱化 / G4 清单棘轮 + git 事实源不变量） |
| `backend/tests/tools/mutate_p2_38_round14.py` | 5 个真实变异，验证闸门能红且能还原 |

**判据为何用 ΔAUC 而非 ΔF1**（自检实测得出，非臆断）：
固定阈值 0.3 下，组级 held-out 令测试组 token 全部 OOV ⇒ TF-IDF 向量近似全零
⇒ LR 输出近似常数 ⇒ 预测退化为全 1 ⇒ **F1 与随机口径完全相同（实测 ΔF1=0.0）**，
无法体现口径差。AUC 与阈值无关，能如实反映「排序质量是否来自兄弟记忆」。

## 七、未验证 / 记账（不得省略）

1. **§五 F5 的 4 处阈值/权重挑优未逐条核实**其评估集是否被污染。
   扫描器只能识别「存在 `best_threshold`/`best_f1` 赋值」这一形态信号，
   **无法判断阈值是在训练折内选还是在评估集上选** —— 必须人工读码，本轮未完成。
2. **`aligned_features.csv` 的 56 个完全重复行**未量化其对 v1_23 划分的影响
   （占比 0.2%，预估可忽略，但未实测）。
3. **未改动任何脚本口径**：本轮只检测不整改，所有发现均为新增记账，
   不构成对既有读数的修正，也不推翻 P2-1/P2-2 的任何结论。
4. `datasets/external/` 第三方副本已排除在审计范围外（且全部未入库），
   若将来它们被纳入本仓评估链路并入库，**必须重新纳入扫描**。
5. **三个未入库脚本未纳入本轮清单**（`models/train_tabular_depression.py`、
   `models/train_text_depression_classifier.py`、`scripts/deep_analysis_fix.py`）。
   它们在本机工作树中存在且各含 1 处 `train_test_split`，但**未交付**，
   按交付形态口径不计入；若将来入库，G4 棘轮会红并强制补审。
5. 本轮**未**执行方向 A（逐症状证据链）与方向 C（隐私 LLM 编码），
   方向 A 的可行性结论见立项文档（受限于「文本」与「逐条目标签」落在不相交数据上）。

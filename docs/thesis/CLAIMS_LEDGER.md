# 论文数字台账（ROUND_36/37 更新；ROUND_29 · P2-56 更新；ROUND_28 · P2-55 建立）

> **纪律**：论文里的每个数字必须能由**已提交产物**用一条命令复算；不得从任何 ROUND 汇报转引。
> **机器校验**（只读，CI 每次提交都跑）：
>
> ```bash
> cd backend
> .venv/Scripts/python.exe scripts/modeling/eval/verify_thesis_numbers.py
> ```
>
> 该闸门从已提交的 csv/json **独立复算**本表每一行的点估计与 95% CI，并核对
> `RESULTS_CHAPTER.md` 的结果表、迁移表、混淆矩阵、诊断表，以及「禁用数字」黑名单。
> `--show` 模式可打印全部复算真值表。

## 〇、怎么读这张表

- **编号**：`C` = 指标读数，`S` = 数据集规模，`X` = 敏感性读数。`REVIEWER_QA.md` 与
  `LIMITATIONS.md` 引用任何数字时必须带编号（闸门强制）。
- **容差**：文档按展示精度书写（4 位小数为主，个别 5 位）；闸门按「半个末位」容差比对。
- **复算分层**：`01/02` 评估脚本需要原始数据集（`datasets/` 不在版本库），只能在有数据的
  机器上跑；**CI 干净 checkout 的复算层是 csv/json**——本闸门与外部审稿人复算入口
  （`--report-only`）在同一层。「提交产物 == 单命令产物」的硬闸门见 ROUND_27
  （`docs/P2_54_ROUND27_TRANSFER_AUDIT.md`）；**ROUND_29 已随 01 全量重跑复验**
  （D-R26-1 修复更换 artifact 后，`--report-only` 与全量运行产物逐字节一致）。
- **口径**：点估计 = 全样本统计量（不是 bootstrap 均值）；CI = 非参数 bootstrap 分位
  （B=10000，seed=42）；判定阈值 0.5。

## 一、可进论文数字

### 1.1 域内（生理模态 · 生产路径 · n = 157 · ROUND_29 修复后工件）

| 编号 | 指标 | 点估计 | 95% CI | 来源产物 | 复算命令 | 类别 | 可否进论文 |
|---|---|---|---|---|---|---|---|
| C-01 | Accuracy | 0.8662 | [0.8089, 0.9172] | `docs/model-evaluation/physio_v2_current_data_eval.json` + `backend/models/artifacts/physiological_optimized/test_predictions.csv` | `01_reproducible_eval.py --report-only`（需数据集）；CI 层 `verify_thesis_numbers.py` | 域内 | ✅ |
| C-02 | Precision | 0.7742 | [0.6667, 0.8750] | 同上 | 同上 | 域内 | ✅ |
| C-03 | Recall | 0.8727 | [0.7800, 0.9531] | 同上 | 同上 | 域内 | ✅ |
| C-04 | F1 | 0.8205 | [0.7387, 0.8889] | 同上 | 同上 | 域内 | ✅ |
| C-05 | ROC AUC | 0.9451 | [0.9064, 0.9768] | 同上 | 同上 | 域内 | ✅ |
| C-06 | 混淆矩阵 | TP=48 / FP=14 / FN=7 / TN=88 | — | 同上 | 同上 | 域内 | ✅ |
| C-07 | 一致性·train-only 重拟合 F1（ROUND_29 起） | 0.8205 | — | 同上（csv 列 `y_score_refit_scaler`） | `01_reproducible_eval.py --report-only`；CI 层 `verify_thesis_numbers.py` | 域内·一致性证明 | ✅（与 C-04 相等即 co-consistency 证据；ROUND_29 前为缺陷定位诊断列，历史读数见 §1.1 注） |
| C-08 | 一致性·train-only 重拟合 Recall（ROUND_29 起） | 0.8727 | — | 同上 | 同上 | 域内·一致性证明 | ✅（同上） |
| C-09 | 一致性·train-only 重拟合 ROC AUC（ROUND_29 起） | 0.9451 | — | 同上 | 同上 | 域内·一致性证明 | ✅（同上） |

> **ROUND_29 修复记录（D-R26-1，路径 B 端到端重训）**：C-01 ~ C-06 是**修复后**生产链路
> 读数（同一 n = 157 测试集、同一阈值 0.5、同一评估脚本）。修复前同口径为
> Accuracy 0.8599 / Precision 1.0000 / Recall 0.6000 / F1 0.7500 / ROC AUC 0.9884 /
> TP=33 / FP=0 / FN=22 / TN=102（历史口径，工件已存档为 `*.broken_round29`，**不可比**，
> 不得作为现行性能引用；修复细节与防复发闸门见 `docs/P2_56_ROUND29_SCALER_FIX_AUDIT.md`）。
> 修复是**标准化缺陷整改，不是模型能力提升**：修复后 AUC 由 0.9884 降至 0.9451。
> C-07 ~ C-09 在 ROUND_29 前是「只换 scaler」的缺陷定位诊断列（当时读数 F1 0.9369 /
> Recall 0.9455 / AUC 0.9841，历史口径，不得宣称为性能）；修复后部署 scaler 与
> train-only 重拟合逐位相等，该列转为 co-consistency 证明列（csv 中与 `y_score`
> 逐位相等，闸门第一层在参数级复判）。

### 1.2 跨数据集迁移（两个「降级」单元；其余 16 格 N/A）

| 编号 | 指标 | 点估计 | 95% CI | 来源产物 | 复算命令 | 类别 | 可否进论文 |
|---|---|---|---|---|---|---|---|
| C-10 | 生理×Kaggle Accuracy（n=10000） | 0.4801 | [0.4701, 0.4898] | `docs/model-evaluation/transfer_physio_kaggle_eval.json` + `backend/models/artifacts/eval_transfer/transfer_physio_kaggle_predictions.csv` | `02_transfer_eval.py --unit physio_kaggle --report-only`（需数据集）；CI 层 `verify_thesis_numbers.py` | 降级 | ✅（必须与「降级/下界」定性同引） |
| C-11 | 生理×Kaggle F1（n=10000） | 0.3639 | [0.3507, 0.3772] | 同上 | 同上 | 降级 | ✅（同上） |
| C-12 | 生理×Kaggle ROC AUC（n=10000） | 0.5120 | [0.5006, 0.5233] | 同上 | 同上 | 降级 | ✅（同上；CI 覆盖 0.5 ⇒ 与随机不可区分） |
| C-13 | 生理×Kaggle Precision（n=10000） | 0.4930 | [0.4756, 0.5108] | 同上 | 同上 | 降级 | ✅（同上） |
| C-14 | 生理×Kaggle Recall（n=10000） | 0.2883 | [0.2762, 0.3008] | 同上 | 同上 | 降级 | ✅（同上） |
| C-15 | 生理×Kaggle 混淆矩阵 | TP=1487 / FP=1529 / FN=3670 / TN=3314 | — | 同上 | 同上 | 降级 | ✅（同上） |
| C-16 | 文本×OOD Accuracy（n=2523） | 0.9945 | [0.9913, 0.9972] | `docs/model-evaluation/transfer_text_ood_eval.json` + `backend/models/artifacts/eval_transfer/transfer_text_ood_predictions.csv` | `02_transfer_eval.py --unit text_ood --report-only`（需数据集）；CI 层 `verify_thesis_numbers.py` | 降级 | ✅（必须同时给出 C-22，不得单独引用） |
| C-17 | 文本×OOD Precision（n=2523） | 1.0000 | [1.0000, 1.0000] | 同上 | 同上 | 降级 | ✅（同上） |
| C-18 | 文本×OOD Recall（n=2523） | 0.9727 | [0.9574, 0.9862] | 同上 | 同上 | 降级 | ✅（同上） |
| C-19 | 文本×OOD F1（n=2523） | 0.9862 | [0.9783, 0.9930] | 同上 | 同上 | 降级 | ✅（同上；高指标是兄弟泄漏证据，不是泛化） |
| C-20 | 文本×OOD ROC AUC（n=2523） | 0.9986 | [0.9956, 0.99999] | 同上 | 同上 | 降级 | ✅（同上） |
| C-21 | 文本×OOD 混淆矩阵 | TP=499 / FP=0 / FN=14 / TN=2010 | — | 同上 | 同上 | 降级 | ✅（同上） |

### 1.3 泛化口径（文本模态，唯一可引用的「泛化」读数）

| 编号 | 指标 | 点估计 | 95% CI | 来源产物 | 复算命令 | 类别 | 可否进论文 |
|---|---|---|---|---|---|---|---|
| C-22 | groupwise F1（n=8379，阈值 0.5） | 0.5864 | [0.5307, 0.6381] | `backend/scripts/modeling/eval/v1_30/groupwise_ci.json`（`metrics.f1`）+ `backend/scripts/modeling/v1_27/groupwise_oof_predictions.csv` | `v1_30/groupwise_ci.py`（生成）；`verify_thesis_numbers.py`（闸门内按 group 重采样独立复算 CI） | 泛化口径 | ✅ |
| C-23 | groupwise ROC AUC（n=8379） | 0.8437 | [0.8170, 0.8696] | 同上（`metrics.roc_auc`） | 同上 | 泛化口径 | ✅ |
| C-24 | groupwise Recall（n=8379） | 0.5375 | [0.4764, 0.5975] | 同上（`metrics.rec`） | 同上 | 泛化口径 | ✅ |
| C-25 | groupwise Precision（n=8379） | 0.6450 | [0.5782, 0.7114] | 同上（`metrics.prec`） | 同上 | 泛化口径 | ✅ |
| C-26 | 文本 groupwise Brier 分数（n=8379） | 0.1280 | [0.1184, 0.1376] | `backend/scripts/modeling/eval/v1_33/calibration_analysis.json`（`units.text_groupwise_oof.metrics.brier`） | `v1_33/calibration_analysis.py`（生成）；`verify_thesis_numbers.py`（点估计独立实现 + CI 同源独立复算） | 泛化口径·校准 | ✅ |
| C-27 | 文本 groupwise ECE（n=8379，10 等宽箱） | 0.0855 | [0.0710, 0.1069] | 同上（`units.text_groupwise_oof.metrics.ece`） | 同上（ECE 用显式区间遍历的独立实现） | 泛化口径·校准 | ✅ |
| C-28 | 文本 groupwise 校准斜率（Platt slope） | 1.3466 | — | 同上（`units.text_groupwise_oof.calibration_slope`） | 同上（Nelder-Mead 最小化 logloss 的独立实现；斜率无 CI，理由见 method.not_estimated） | 泛化口径·校准 | ✅ |
| C-29 | 生理切分 ECE（n=157） | 0.2160 | [0.1815, 0.2647] | 同上（`units.physio_current_split.metrics.ece`） | 同上 | 次级口径·小样本 | ⚠️ 必须同句标注 n=157 |
| C-30 | 生理×Kaggle Brier（n=10000） | 0.2761 | [0.2729, 0.2793] | 同上（`units.physio_kaggle.metrics.brier`） | 同上 | 降级·跨数据集下界 | ❌ 仅压力测试，禁作外迁 |
| C-31 | 文本×OOD(strict) Brier（n=2523） | 0.0281 | [0.0264, 0.0299] | 同上（`units.text_ood_strict.metrics.brier`） | 同上 | 降级·兄弟泄漏 | ❌ 仅压力测试，禁作外迁 |
| C-32 | 文本 groupwise DCA 净获益 NB(t=0.50) | 0.0523 | — | 同上（`units.text_groupwise_oof.dca.net_benefit_model`，阈值 0.50 处） | 同上（独立实现 TP/n − FP/n·(t/(1−t))） | 泛化口径·决策曲线 | ✅ |
| C-33 | 文本 groupwise DCA 净获益 NB(t=0.05) | 0.1763 | — | 同上（阈值 0.05 处） | 同上 | 泛化口径·决策曲线 | ✅ |
| C-34 | 安全网工作点净 Recall（t_low=0.11, t_high=0.60） | 0.9845 | [0.9683, 0.9972] | `backend/scripts/modeling/eval/v1_36/safety_net_analysis.json`（`operating_point.operating_point.net_recall`） | `v1_36/safety_net_analysis.py`（生成）；`verify_thesis_numbers.py`（flatnonzero 独立复算 + 同源 group bootstrap CI） | 泛化口径·漏报安全网 | ✅ 必须与 C-35 同引 |
| C-35 | 同工作点需人工介入比例 | 0.8125 | — | 同上（`review_burden`） | 同上（恒等式 burden = P(p≥t_low)，已数值核验） | 泛化口径·漏报安全网 | ✅ 必须与 C-34 同引 |
| C-36 | 安全网区间阳性率（[0.11, 0.60)） | 0.1905 | — | 同上（`sn_precision`） | 同上 | 泛化口径·漏报安全网 | ✅ 须同句注明低于基准率 0.2163 |
| C-37 | 安全网工作点预警精确率（只对 p≥0.60 负责） | 0.6815 | — | 同上（`alert_precision`） | 同上 | 泛化口径·漏报安全网 | ✅ 必须与 C-38 对比引用 |
| C-38 | 单阈值直接下调到 0.11 的精确率（成本等价对照） | 0.2620 | — | 同上（`cost_equivalence.single_threshold_at_t_low.precision`） | 同上 | 泛化口径·漏报安全网 | ✅ 必须与 C-37 对比引用 |

> C-22 ~ C-25 备注：这些是**跨被试（按原始用户分组、组间不重叠）**的泛化读数，CI 为
> **按 group 重采样**的分组级 bootstrap（B=10000, seed=42，抽 1277 组非按行）——
> 同一学生的原文+增强副本在组内相关，按行 bootstrap 会低估区间。同一模型在同一批数据上的
> 随机划分读数是 F1 0.9964 / AUC 0.9994——那是兄弟泄漏口径，**不得**当泛化引用
> （见 `docs/EVALUATION_INTEGRITY_REPORT.md`）；分组口径相对随机口径的落差
> F1 −0.41 / AUC −0.156 即虚高幅度。该口径为「同人群换被试」，**不外推到跨平台/跨人群**。
>
> **随机划分读数溯源（ROUND_34 补记）**：F1 0.9964 / AUC 0.9994 的来源产物是已提交的
> `backend/scripts/modeling/v1_27/bilingual_groupwise_retrain_results.json` 的
> `textwise_ooF`（n=8379）。只读复算：
> `cd backend && .venv/Scripts/python.exe -c "import json;d=json.load(open('scripts/modeling/v1_27/bilingual_groupwise_retrain_results.json',encoding='utf-8'));print(d['textwise_ooF'])"`。
> `docs/ML_LEAKAGE_AUDIT.md:172` 的 0.8860 是另一协议（随机文本级、1244 组、阈值 0.3），
> 与本条 0.9964 不可比，非矛盾。

### 1.4 融合权重敏感性（`docs/model-evaluation/fusion_weight_sensitivity.csv`）

> 口径：三模态分数固定为 5 组手写场景（agree_low 20/15/18、agree_high 85/90/88、
> conflict_s-low_t-high 20/90/25、conflict_s-high_t-low 85/15/80、mid_all 50/55/52），
> 结构化权重 w_structured 在 0.35–0.75 扫描（w_text : w_physio 恒为 2:1，权重和 = 1）；
> risk_score = 加权平均，risk_level 按融合档阈值 22/42/62/82 分档。
> 生成脚本未入库 ⇒ 闸门复算的是 csv 的**内部一致性**（公式 + 阈值表 + 生产权重行存在）。

| 编号 | 读数 | 点估计 | 95% CI | 来源产物 | 复算命令 | 类别 | 可否进论文 |
|---|---|---|---|---|---|---|---|
| X-01 | agree_low 风险等级对权重不敏感 | 0 级（9/9 行） | — | `docs/model-evaluation/fusion_weight_sensitivity.csv` | `verify_thesis_numbers.py` | 敏感性 | ✅ |
| X-02 | agree_high 风险等级对权重不敏感 | 4 级（9/9 行） | — | 同上 | 同上 | 敏感性 | ✅ |
| X-03 | mid_all 风险等级对权重不敏感 | 2 级（9/9 行） | — | 同上 | 同上 | 敏感性 | ✅ |
| X-04 | conflict_s-low_t-high 随结构化权重增大由 2 级转 1 级 | 2→1 @0.55 | — | 同上 | 同上 | 敏感性 | ✅ |
| X-05 | conflict_s-high_t-low 随结构化权重增大由 2 级转 3 级 | 2→3 @0.55 | — | 同上 | 同上 | 敏感性 | ✅ |
| X-06 | 生产权重在扫描范围内 | 0.55/0.3/0.15 | — | 同上 + `backend/app/ml/fusion_engine.py::DEFAULT_WEIGHTS`（AST 取值） | `verify_thesis_numbers.py` | 敏感性 | ✅ |
| X-07 | 三模态一致时（极差<20）消融最大等级翻转（级） | 1 | — | `backend/scripts/modeling/eval/v1_37/fusion_ablation.json`（`summary.*.by_stratum.agree.max_abs_delta`） | `v1_37/fusion_ablation.py`（生成）；`verify_thesis_numbers.py`（调生产引擎独立重算） | 融合消融·合成网格 | ✅ 必须同句注明输入为合成网格 |
| X-08 | 仅剩生理模态时的等级翻转率（冲突层） | 0.86 | — | 同上（`summary.only_physiological.by_stratum.conflict.flip_rate`） | 同上 | 融合消融·合成网格 | ✅ 必须同句注明输入为合成网格 |
| X-09 | 最大翻转个案 (0,0,90)：完整 vs 仅生理的等级差（级） | 4 | — | 同上（`worst_cases[0]`） | 同上 | 融合消融·合成网格 | ✅ 必须同句注明输入为合成网格 |

### 1.5 数据集规模

| 编号 | 项 | 点估计 | 95% CI | 来源产物 | 复算命令 | 类别 | 可否进论文 |
|---|---|---|---|---|---|---|---|
| S-01 | depresjon 生理数据集行数 | 1029 | — | `docs/model-evaluation/physio_v2_current_data_eval.json`（`dataset.rows`） | `01_reproducible_eval.py --report-only`；CI 层 `verify_thesis_numbers.py` | 数据集 | ✅ |
| S-02 | Kaggle Wearable 行数 | 10000 | — | `docs/model-evaluation/transfer_physio_kaggle_eval.json`（`dataset.rows`） | `02_transfer_eval.py --unit physio_kaggle --report-only`；CI 层 `verify_thesis_numbers.py` | 数据集 | ✅ |
| S-03 | OOD strict 子集行数 | 2523 | — | `docs/model-evaluation/transfer_text_ood_eval.json`（`dataset.rows`） | `02_transfer_eval.py --unit text_ood --report-only`；CI 层 `verify_thesis_numbers.py` | 数据集 | ✅ |
| S-04 | PHQ-9 数据集行数 | 682 | — | `docs/model-evaluation/TRANSFER_MATRIX.md`（跨文档对齐；原始 csv 不在版本库，无 json 工件记行数 ⇒ 不可复算，只作规模陈述） | `verify_thesis_numbers.py`（对齐检查） | 数据集 | ✅（仅作数据集规模陈述，不关联任何指标） |
| S-05 | groupwise 语料行数 | 8379 | — | `backend/scripts/modeling/v1_27/groupwise_oof_predictions.csv` | `verify_thesis_numbers.py`（行数复算） | 数据集 | ✅ |
| S-06 | 域内切分 train/val/test | 719 / 153 / 157 | — | `docs/model-evaluation/physio_v2_current_data_eval.json`（`dataset.split`） | `01_reproducible_eval.py --report-only`；CI 层 `verify_thesis_numbers.py` | 数据集 | ✅ |
| S-07 | 域内测试集 n | 157 | — | 同上（`meta.n`）+ csv 行数 | 同上 | 数据集 | ✅ |
| S-08 | depresjon 类别分布（阴性/阳性） | 670 / 359 | — | 同上（`dataset.class_counts`） | 同上 | 数据集 | ✅ |

## 二、禁用数字黑名单（不得作为「结果」引用）

> 以下数字**出现在论文里即视为学术不诚信**（历史口径/变更说明除外，且必须与拒绝标记同行）。
> 闸门对四份论文文档做行级扫描：命中禁用 token 且同行无拒绝标记 ⇒ 红。

| 编号 | 数字 | 出处 | 为何禁用 | 正确替代 |
|---|---|---|---|---|
| B-01 | 0.8993 / 0.9318 / 0.7885 / **0.8542** / **0.9653**（优化版）与 0.6600 / 0.6091 / 0.8933 / **0.7243**（原始版），样本量 n=139 | `docs/upgrade_baseline_202607.md:19-20`、`backend/models/artifacts/physiological_optimized/metrics.json` | **不可复现**（三重证据）：仓内 `stratified_split`（rs=42）恒给 719/153/157 而非记录的 719/171/139；修复前 artifact `scaler.json` 统计量与仓内三份生理数据全不匹配（sleep_quality 均值 5.43 超出 1-5 量表，该工件已存档为 `scaler.json.broken_round29`）；训练脚本从未入库。只能作历史口径/变更说明 | C-01 ~ C-06（n=157 新口径） |
| B-02 | registry `test_f1` = **0.9530** | `backend/app/core/model_registry.py:158` | **禁用**：第三套数字——`artifact_metadata` 记 hidden_dims [64,32,16] / dropout 0.3，与 `model.json` 实际 [128,64,32,16] / 0.2 不符；`manifest.json` 已自认过期 | C-04（0.8205）；引用 registry 元数据时必须显式标注过期 |
| B-03 | **0.8527** | `docs/model-evaluation/physio_v2_test_ci.json`（已标 SUPERSEDED） | bootstrap 均值被误写入 `point` 位（名义值 0.8541667 亦属 B-01，两者差 0.0015 即来源） | C-04（0.8205，全样本统计量） |
| B-04 | 融合「4 条手写场景全 1.0000」行 | `docs/upgrade_baseline_202607.md:22` | 4 条硬编码场景无统计意义；且 `1.0000` 与合法 Precision=1.0000（C-02/C-17）**撞号**，无法做 token 级闸门，仅叙事禁用 | X-01 ~ X-06（权重敏感性扫描） |
| B-05 | 任何台账外、未复算的数字 | — | 通则：没有来源产物路径 + 复算命令的数字一律不得进论文 | 先补登记（复算通过）再引用 |

## 三、历史文件保留说明（不删，只标注）

- `docs/model-evaluation/physio_v2_test_ci.json`：Hanley-McNeil 解析近似 + 0.8527 误记，
  顶部已标 SUPERSEDED，保留作变更记录；**不得**从中取任何数字。
- `docs/upgrade_baseline_202607.md`：v1.3→v1.4 升级基线档案，其中生理两行（B-01）与
  融合行（B-04）仅作历史口径。
- `backend/models/artifacts/physiological_optimized/*.broken_round29`：ROUND_29 修复
  D-R26-1 前的生产工件存档（scaler / cleaner / model / metrics 四件，字节级保留，
  侧车校验相符；feature_names 十三特征名两代相同，未入存档）。其中的参数（如 scaler
  sleep_quality 均值 5.4279）只可用于论证**修复前**缺陷，修复后一切读数以
  C-01 ~ C-09 为准。
- `backend/app/core/model_registry.py` 的 `artifact_metadata`（B-02）：本轮**不改**
  registry（边界），只在台账与论文里标注其不可引用。

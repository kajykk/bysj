# P2_53 · ROUND_26（G1）审计：把评估数字变成外部可核验的证据

> 状态：起点 HEAD `b2243f8`（ROUND_25，CI 10/10）。
> 定位：**G1 = 证据可复算化**（G2 外部迁移、G3 预注册冻结不在本轮）。
> 本轮的门槛是**数字门槛**（可复算/自洽/CI 口径/可核验/不得自证），不是用例门槛。
> 全部读数为 2026-10-23 实测。

## 〇、一句话结论（先说最重要的）

1. **原 139 行测试集不可复现**——不是因为「懒得复现」，而是三条独立证据都指向
   「artifact 的训练数据版本不在仓内」：切分函数恒给 719/153/157、`
   scaler.json` 统计量与仓内三份数据全不匹配、artifact scaler 变换当前数据后 z 分数整体偏移。
   ⇒ 旧数字（F1 0.8542 / AUC 0.9653 / Hanley-McNeil CI）**只能作历史记录**，已标注取代关系。
2. **新的可核验证据已建立**：逐样本预测 `test_predictions.csv`（157 行 + `.sha256`）、
   bootstrap CI（B=10000, seed=42）、一条命令复算、连跑两次字节一致。
3. **顺带查出一条生产缺陷**：artifact 的 `scaler.json` 与数据/cleaner 版本不配套，
   生产链 recall 只有 **0.6000**（每 10 个真实阳性漏 4 个），而模型权重本身正常
   （重拟合 scaler 的对照口径 F1 0.9369）。已记为缺陷 D-R26-1，本轮**不重训、不改 artifact**。

---

## 一、开工前置实测（§〇 五项逐条核对）

| 项 | 提示词转引 | 本轮实测 | 结论 |
|---|---|---|---|
| HEAD | b2243f8 | `git rev-parse HEAD` = `b2243f8` = origin/main | 一致 |
| `physio_v2_test_ci.json` 由谁生成 | 「无人生成」 | `git grep` 仅命中 README 与自身；仓内无生成脚本 | 确认 |
| 逐样本分数 | 无 | artifact 目录仅 7 个文件，无 score 文件 | 确认 |
| f1 两套数 | 0.8541667 vs 0.8527 | 名义值 0.8541667（`metrics.json`）；0.8527 = bootstrap 均值（见 §T2） | 已查清 |
| artifact 可加载 | 是 | `load_all_artifacts()` 成功：input_dim=13、feature_names 13 列、13,153 参数 | 确认 |
| manifest 矛盾 | status=TRAINING_PENDING | registry `enabled=True/lifecycle="default"`，predict.py 直接加载本目录 | manifest 过期（§T4） |

补充实测（提示词未列，但决定了 T1 的走法）：

- `datasets/physiological/external/depresjon_processed/depresjon_physiological.csv`：
  **1029 行**，label 分布 **670 阴性 / 359 阳性** —— 正好等于 719+171+139。
- 仓内**没有任何脚本**产出 `physiological_optimized`（`grep -rn "hidden_dims=\[128"` 零命中；
  `git log --all -S "physiological_optimized"` 只命中 artifact 与文档）⇒ 训练脚本从未入库。
- `app/ml/data_split.py::stratified_split` 的两个历史版本（341f22c、8c4f76b）**逐行相同**，
  主算法从未变过（只有 M-ML-3/M28 的 0 样本保护与空切分守卫）。

## 二、T1 · 评估脚本与产物

### 2.1 交付物

| 产物 | 路径 | 说明 |
|---|---|---|
| 评估脚本 | `backend/scripts/modeling/eval/v1_29/01_reproducible_eval.py` | 三种模式：默认全量、`--verify-original` 诊断、`--report-only` 复算 |
| 逐样本预测 | `backend/models/artifacts/physiological_optimized/test_predictions.csv` | 157 行；列 `sample_id,row_index,y_true,y_score,y_pred,y_score_refit_scaler` |
| 校验和 | `.../test_predictions.csv.sha256` | `539617fb83665de4dda1e646eae35703d194c9eb87f874aa02c62cf767c81d09` |
| 新 CI json | `docs/model-evaluation/physio_v2_current_data_eval.json` | `method = "bootstrap over persisted per-sample scores"` |
| 人读报告 | `docs/model-evaluation/PHYSIO_V2_EVAL_REPORT.md` | 由脚本生成，n 写在第一行 |

### 2.2 推理链（复刻生产，而不是另写一套）

`DataCleaner.transform`（artifact cleaner_stats）→ `engineer_features`（13 列）
→ `SimpleStandardScaler.transform`（artifact scaler）→ `PhysiologicalMLP.predict_proba`，
与 `predict.py::_predict_physiological_sync` 同一套工件与同一顺序。

脚本**复用** `app.ml.model_loader` 的四个 loader（不另写加载器；
`load_cleaner` 带 `require_checksum=True`，artifact 被篡改会直接抛错）。

### 2.3 「原切分能否复现」的测试（`--verify-original`）

| 候选切分 | 输出（train/val/test） | 命中 719/171/139 |
|---|---|---|
| 项目 `stratified_split`（0.7/0.15/0.15, rs=42） | **719 / 153 / 157** | ✗ |
| sklearn 两阶段 mid=0.3 / second=0.45 | 720 / 169 / 140 | ✗ |
| sklearn 两阶段 mid=0.3 / second=0.5 | 720 / 154 / 155 | ✗ |
| sklearn 两阶段 mid=0.3 / second=0.55 | 720 / **139** / 170 | ✗（val/test 对调且 train 差 1） |
| 其余 3 个变体 | 720/154/155、720/169/140、720/139/170 | ✗ |

`--verify-original` 的判定：`matched = []`、`reproducible = false`、退出码 2。
**本脚本因此不冒充原测试集**：它评估的是「当前仓内数据的确定性切分」，
在报告与 json 里显式写 `dataset = depresjon_physiological.csv@当前版本`。

### 2.4 为什么断定「训练数据不在仓内」——三条独立证据

| # | 证据 | 实测 |
|---|---|---|
| E1 | 切分函数恒定性 | 唯一函数、两个历史版本逐行相同、在 1029 行（670/359）上必给 719/153/157；记录的 171/139 无任何仓内候选可生成 |
| E2 | scaler 统计量不可能来自仓内数据 | `mean[1] = 5.4279`（sleep_quality），而 depresjon 该列值域 1-5（均值 2.83）、augmented 同（2.83）、kaggle 无此列（Mood_Rating 均值 5.07 但量纲 1-10 且列映射不成立） |
| E3 | 用 artifact scaler 变换当前数据后的 z 分数 | 13 列中 6 列 \|mean_z\| > 0.5，其中 sleep_quality **-1.002**、steps **-1.406**；若同分布应 ≈ 0 |
| E4（旁证） | artifact 内部不一致 | `cleaner_stats.json` 的 medians 与当前数据 **3/4 精确匹配**（sleep_quality 3.0、systolic 117、diastolic 76；exercise 44 vs 43），而 `scaler.json` 完全对不上 ⇒ 两者不可能来自同一次 `fit(train)` |

**结论**：模型权重是「depresjon 某版本」训练的（E5：重拟合 scaler 后全量 F1 0.8827，
说明模型学到了这个数据的模式），但 `scaler.json` 与训练数据版本不配套，
且该版本数据不在仓内。原 139 行指标属**不可复现的历史记录**。

### 2.5 新证据的数字（生产路径，n = 157）

| 指标 | 点估计 | 95% CI（bootstrap B=10000, seed=42） |
|---|---|---|
| Accuracy | 0.8599 | [0.8025, 0.9108] |
| Precision | 1.0000 | [1.0000, 1.0000] |
| Recall | **0.6000** | [0.4687, 0.7288] |
| F1 | 0.7500 | [0.6383, 0.8431] |
| ROC AUC | 0.9884 | [0.9694, 0.9990] |

混淆矩阵：TP=33 / FP=0 / FN=22 / TN=102。

诊断对照（**非生产**口径，仅把 scaler 换成「在当前训练集重拟合」）：

| 口径 | F1 | ROC AUC | Recall |
|---|---|---|---|
| 生产路径（artifact scaler） | 0.7500 | 0.9884 | 0.6000 |
| 诊断（重拟合 scaler） | **0.9369** | 0.9841 | 0.9455 |
| 生产路径（全量 1029 行对照） | 0.6800 | 0.9624 | 0.5209 |
| 重拟合（全量 1029 行对照） | 0.8827 | 0.9722 | — |

AUC 两口径都 ≈0.98 ⇒ 排序能力正常，**问题在标准化参数**（D-R26-1）。

## 三、§二 五条门槛的读数

| 门槛 | 判定方式 | 读数 |
|---|---|---|
| 1 可复算 | 同一命令连跑两次，比对三个产物的 sha256 | csv `539617fb…` = `539617fb…`；json `08246dec…` = `08246dec…`；report `393c5662…` = `393c5662…` ⇒ **PASS** |
| 2 自洽 | 由 csv 逐行数出 n/TP/FP/FN/TN，与 json `meta` 逐项比对 | csv 157/33/0/22/102 = json 157/33/0/22/102 ⇒ **PASS**（与旧 meta 139/41/3/11/84 不一致，原因见 §2.4，属「解释差异来源」路径） |
| 3 CI 口径 | `grep -c Hanley 报告` | **0**；所有指标（含 AUC）CI 均由 bootstrap 分位给出 ⇒ **PASS** |
| 4 可核验 | 一条命令从 csv 复算全部数字 | `--report-only` 重算并重写报告，数字与 json 一致 ⇒ **PASS** |
| 5 不得自证 | 变异：把 csv 中一条 `y_true=1` 改为 `0`，重跑 `--report-only` | 基线 F1 0.7500/AUC 0.9884/FN 22/TN 102 → 变异后 F1 **0.7586**/AUC **0.9872**/FN 21/TN 103 ⇒ 数字随 csv 变化，**PASS**（变异后已还原，csv sha256 复原为 `539617fb…`） |

环境指纹（写入 json `reproducibility.env`）：Python 3.13.12 / numpy / pandas / scikit-learn
版本号见 json；artifact 四个文件的 sha256 也一并落盘，便于「换机器重跑」时定位差异来源。

## 四、T2 · 口径统一（不许留两套数）

### 4.1 f1 两套数的根因（已查清）

| 数 | 值 | 来源 |
|---|---|---|
| `metrics.json` 的 `test_metrics.f1` | **0.8541666666666667** | 全样本名义值 `2TP/(2TP+FP+FN)` = 82/96 |
| 旧 `physio_v2_test_ci.json` 的 `f1.point` | **0.8527** | **bootstrap 均值**（重采样统计量） |

复算证据（用旧混淆矩阵 41/3/11/84，B=10000, seed=42，多项分布重采样）：
`acc` 均值 0.899340、`prec` 0.931933、`rec` 0.789113、**`f1` 0.853275**。
四者中只有 f1 与旧 json 的 point **明显不同**（0.8533 vs 0.8527，而名义值 0.8542）；
acc/prec/rec 在四位小数上与名义值不可区分，因此旧文件的「point」位混用了两种口径。

> 旧 json 的 bootstrap 均值 0.853275 与它记录的 0.8527 仍差 0.0006：旧生成脚本未入库，
> 无法逐位复现其重采样实现（可能用样本级重采样而非多项分布）。**这本身也是「不可复现」的一部分**，
> 已记入旧 json 的 `_method_notes`。

### 4.2 处置

1. 旧 `physio_v2_test_ci.json` **保留**（历史记录不删），顶部新增
   `_status: SUPERSEDED`、`_reproducibility: NOT REPRODUCIBLE`、`_method_notes` 三条口径说明。
2. 新 json 明确 `point_estimator: "full-sample statistic (not bootstrap mean)"`。
3. `docs/model-evaluation/README.md` §1 增加复核块：说明旧证据不可复现、AUC 近似已作废、
   新旧数字不可混用、论文引用须改用新证据。

## 五、T3 · 外部数据集登记表

`docs/model-evaluation/DATASETS.md`（新建）登记 **6 条**（超过提示词要求的 4 类）：

1. Depresjon（生理，本轮评估数据源）
2. Kaggle Wearable（生理，未参与训练，G2 迁移首选）
3. PHQ-9 Dataset 5th Edition（682 行量表）
4. actverse / acttrust（R 包，**GPL-3.0**，标注「不建议直接用于 G2」）
5. MMPsy（**MIT**，1,275 学生，论文 arXiv:2408.12088）
6. 中文抑郁语料 v1/v2（MMPsy 派生，列结构一致、`augmentation`/`source_idx` 可溯源）

字段齐（名称/来源/版本或日期/许可/引用要求/是否已用于训练/拟用于何种评估/纳入日期），
并对「许可未在仓内留下证据」的条目（Depresjon、Kaggle、PHQ-9）**如实标「未知」**，不代填许可。
本轮未跑任何外部评估。

## 六、T4 · registry / manifest 矛盾：结论与处置

### 6.1 结论：**manifest 过期**，生产实际使用 v2

| 证据 | 内容 |
|---|---|
| `model_registry.py:142-146` | `physiological_model_v2_dl`：`enabled=True`、`lifecycle="default"`、path 指向本目录 `model.json` |
| `predict.py:1006-1023` | `_predict_physiological_sync` 直接 `load_model()/load_scaler()/load_cleaner()` 加载本目录；工件缺失时 **503 → L4 启发式** |
| 全仓 grep | **不存在**「回退到 physiological(v1) 模型」的推理路径；`artifacts/physiological/metrics.json` 只被 dashboard 展示代码读取 |
| manifest 原文 | 「该资产未在 v1.28-final 中交付，生产环境仍使用 physiological (v1) 模型并通过 graceful degradation 降级」⇒ 与代码不符 |

### 6.2 处置：manifest 加显式说明（保留历史，不篡改）

`manifest.json` 新增 `_audit_note_round26`（date / verdict / evidence×3 / also_stale / kept_for_history），
**保留原 `status: TRAINING_PENDING` 与 description 原文**；`manifest.json.sha256` 同步更新为
`4b61c519…`。不改 registry 启用状态（边界）。

### 6.3 附带发现：registry 的 `artifact_metadata` 也是过期数字（第三套）

| 字段 | registry 记录 | artifact 实际 |
|---|---|---|
| `hidden_dims` | [64, 32, 16] | **[128, 64, 32, 16]**（`model.json`） |
| `dropout_rate` | 0.3 | **0.2** |
| `use_batch_norm` | True | True（一致） |
| `test_f1` | 0.9530 | **0.8541667**（`metrics.json`） |
| `test_accuracy` | 0.9660 | **0.8992805** |
| `test_roc_auc` | 0.9940 | **0.9652962** |
| `training_date` / `dataset` | 2026-05-07 / Depresjon n=1029 | 训练时间戳 **2026-06-26T12:49:55Z**（`metrics.json`） |

⇒ 同一个 artifact 存在**三套互不相符的数字**（registry 0.9530 / metrics 0.8542 / 旧 CI 0.8527）。
本轮只登记不改代码（边界：不动 registry 启用状态；元数据修正涉及发布口径，需单独决策），
但**任何对外材料不得引用 registry 的 0.9530**。

### 6.4 缺陷 D-R26-1（新增，P0 级临床风险）

**标题**：`physiological_optimized` 的 `scaler.json` 与 `cleaner_stats.json`/当前数据版本不配套，
导致生产链概率整体偏低、阈值 0.5 下漏诊率 40%。

**证据**：§2.4 的 E2/E3/E4；§2.5 的生产 vs 重拟合对照（recall 0.6000 vs 0.9455）。
**影响**：凡走 `_predict_physiological_sync` 的调用（L1 主模型）都受影响；
抑郁筛查场景下漏诊方向比误诊更危险（precision 1.0 但 recall 0.60）。
**本轮不做**：不重训、不改 artifact、不改推理逻辑（边界）。
**建议**：下一轮（G2 前置）用同一训练管线重拟合 scaler 并重出 artifact，
同时补「artifact 内部一致性闸门」（cleaner/scaler/metrics 必须来自同一次训练，可用训练集统计量交叉校验）。

## 七、回归读数与产物清单

| 项 | 读数 |
|---|---|
| 受影响测试（unit/test_v128_quality_regressions + api/test_fusion_enhanced + api/test_user_data + p2_10 + p2_11） | **269 passed**（8 warnings，63.03s） |
| `p2_10` 全称注释棘轮 | 116（本轮未在 `app/**` 新增全称注释，不变） |
| `#35` 桶计数 | W=109 / X=116 / G=8 / 总数 341（未接线，不变） |
| README 用例数 | 7,548（未新增测试文件，不变） |
| 新增文件 | 脚本 1、产物 3（csv/sha256/json）、报告 1、DATASETS.md 1、本审计 1 |
| 修改文件 | `physio_v2_test_ci.json`（加历史标注）、`model-evaluation/README.md`、`manifest.json` + `.sha256` |

### 7.1 CI 首轮红项（`6db38c1`）与修复（可归因）

`backend-coverage` 在首轮报红，两处**均系本轮新增脚本被既有闸门捕获**，不是缺陷回归：

| 红项 | 闸门 | 原因 | 修复 |
|---|---|---|---|
| `ML 划分入口涉及文件数 41 != 基线 40` | `test_p2_38_leakage_audit_guard` | 新评估脚本的 `verify_original()` 含 2 处 `train_test_split`（穷举候选切分，不产出对外指标）⇒ files 40→41、entries 88→90 | 基线 `BASELINE_FILES=41 / BASELINE_ENTRIES=90` + `BASELINE_FILE_SET` 加该文件 + 注释写明「诊断用途、不吃标签豁免」 |
| `对外材料里找不到字面量：41 个交付脚本 / 90 处…` | `test_p2_46_round22_portfolio_docs` | 同上，对外材料的数字随之变化 | README 三处、`EVALUATION_TRUST_SUMMARY.md` 一处同步 41/90；`test_p2_46` 的自证样本 88→90 |
| （同批）`docs/ML_LEAKAGE_AUDIT.md` 清单 | 人工同步 | 清单标题/汇总/区域表 | 标题与汇总改 41/90；D 区加一行（新脚本 2 入口，标签「诊断用途」）+ ROUND_26 补记 |

修复后本地复验：`p2_38 + p2_46 + p2_10 + p2_11` = **270 passed**（44 warnings, 124.65s）。

**未验证记账**：

- 环境的「换机器重跑仍一致」只做到**版本指纹落盘**（未在第二台机器实跑）；
  numpy 的浮点累加顺序在跨架构（x86 vs ARM）下理论上有差异，已把环境指纹写进 json 供比对。
- 旧的 bootstrap 实现未入库，无法逐位复现旧 CI（只能复现口径结论：point 混用了 bootstrap 均值）。
- 生产链的「批量 transform」与线上「逐样本 transform_single」在 median/winsor 上共用同一份统计量，
  但未做逐样本等价性断言（本轮以批量复刻；建议下轮补一条 1 行 vs 批量一致性用例）。
- 本轮没有新增 pytest 用例（G1 的验收对象是数字与产物，不是代码断言）；
  若后续要把「两跑一致」纳入 CI，需要一条读 `test_predictions.csv` 的闸门——本轮未做，记账。

# 方向 B.5：泄漏补救轮（R14 教训的执行）

> 轮次标记：**B.5**（2026-10-19）。不用「R15」是因为 `docs/planning/P2_R15_CLINICAL_READINESS.md`
> 已占用该编号，避免混淆。
>
> 上游：`docs/ML_LEAKAGE_AUDIT.md`（检测轮，commit `be28cae`）。
> 本轮的边界：**收回结论 + 代码护栏 + 升闸门 + 了结未验证项**，不改任何历史读数。

---

## 〇、L4 证据复现（先实测再动手）

`backend/scripts/modeling/v1_24/01_build_mmpsy_features.py:66`

```python
def derive_stress(phq9: float) -> float:
    return round(phq9 / 27.0 * 5.0, 4)
```

本机实测（`data/external/mmpsy_scores.csv` + `data/processed/mmpsy_structured_features.csv`）：

| 量 | 实测值 |
|---|---|
| `corr(stress_level, phq9_score)` | **1.0**（确定性单调变换） |
| 单特征 AUC（`stress_level` → `phq9_binary`） | **1.0000** |
| 标签阈值干净度 | `phq9_binary=1` 最小 10 分，`=0` 最大 9 分 |

**泄漏范围（提示词要求确认的训练集干净性，已实测）**：

| 数据 | `corr(stress_level, phq9_total)` | 判定 |
|---|---|---|
| `aligned_features.csv`（682 行 phq9 子集） | **0.5476** | 非派生（每个 `phq9_total` 对应 2–4 个不同 `stress_level`）⇒ **干净** |
| `mmpsy_structured_features.csv`（1275 行） | **1.0** | 派生 ⇒ **污染** |

⇒ 泄漏**仅限 mmpsy 外部验证**，v1.23 训练侧未被污染。与提示词预期（≈0.55）一致。

---

## 一、T1：收回被污染的科学结论

### 1.1 污染深度：比提示词点名的范围更大

提示词点名 `mmpsy_external_validation_report.md:28-29` 的「3-feature 5-fold CV AUC 0.9993」
与「AUC gap −0.3744（插补噪声/回归均值）」。实测确认该结论无效，并**发现两层更深污染**：

**（a）本机复现 3f 读数，并量化泄漏红利**（mmpsy 上重训 LR，5-fold StratifiedKFold，seed=42）：

| 特征集 | CV AUC |
|---|---|
| 12f（含 `stress_level`，`02_validate_mmpsy.py:84` 的 `FEATURES`） | **0.9997** |
| 11f（剔除 `stress_level`） | 0.9212 |
| 10f（再剔除 `anxiety`） | 0.6394 |
| **3f（`stress_level, anxiety, panic_attack`，报告值）** | **0.9993** ✅ 逐位复现 |
| 2f（3f 剔除 `stress_level`） | 0.9197 |
| 1f（`stress_level` 单特征） | **1.0000** |

⇒ 「0.9993」确由 `stress_level` 单独造成；把它解释为「3 个有效派生特征的判别力」是同义反复。

**（b）跨口径：go/no-go 依据的 0.6249 与 0.9993 不可比。**

| 读数 | 口径 | 数据来源 |
|---|---|---|
| 0.6249（go/no-go 依据） | **冻结 v1.23 pipeline 跨域推理**（不重训） | 用训练好的模型在 mmpsy 上推理 |
| 0.9993（报告 3f） | **域内重训**（mmpsy 上现训 LR） | `02_validate_mmpsy.py:87` `cross_val_score` |

前者未吃到泄漏红利（所以只有 0.6249），后者吃到（同数据同款重训会得 0.9997）。
⇒ `-0.3744` 这个 gap 是**两种口径之差**，「插补特征引入噪声 → 回归均值效应」的因果解释无效。

**（c）12f 也含泄漏特征** ⇒ go/no-go 表格里 12f 侧的 AUC 0.6249 处在「含泄漏特征的特征空间」中，
但它本身因未重训而未实现泄漏红利。已逐条记账（见 1.3 表「影响判定」列）。

### 1.2 更正清单（历史快照只追加，原文一律保留）

统一格式：在原文段落上方加 `> ⚠️ 更正（B.5，2026-10-19）：…` 块 + 指向本文件。

| # | 文件 | 行 | 原文摘录 | 更正理由 |
|---|---|---|---|---|
| 1 | `archive/2026-09/planning/v1.24-mmpsy-external-consistency-and-score-stability/mmpsy_external_validation_report.md` | 26（块）/28-29（原文） | 「3-feature 5-fold CV AUC 0.9993」「AUC gap (12f−3f) −0.3744 (imputed features may introduce noise → regression-to-mean)」 | 两值无效 + 跨口径（§1.1b）；`stress_level` AUC=1.0 |
| 2 | 同目录 `05-test-plan.md` | 52（块）/51（原文） | 「AUC_3feature 在 [0.5,1.0] 范围内 (实际: 0.9993, 因特征直接从gt派生)」「AUC_gap = -0.3744 (负值说明填充特征引入噪声)」 | **该验收项自陈「因特征直接从gt派生」却仍勾选通过**——当场已知情，未阻止结论被采信；勾选无效 |
| 3 | 同目录 `v1_24_go_no_go_recommendation.md` | 17（块）/约束 AUC 0.6249 行 | 「约束 AUC 0.6249 ≥ 0.80 ❌ 未达标」 | 记账：0.6249 未被 L4 污染（跨域推理未吃到红利），决策读数本身成立；但同表 12f 侧处在含泄漏特征空间 |
| 4 | 同目录 `v1_24_go_no_go_recommendation.md` | 35（块）/结论段 | 「9 个字段无一与 v1.23 的 12 个特征直接映射，缺失值填充导致回归均值效应，削弱了分数区分能力」 | 「回归均值效应」归因无效（跨口径）；「特征覆盖度 50%」结论仍成立 |
| 5 | 同目录 `DELIVERY_REPORT.md` | 32（块）/交付摘要 | AUC 0.6249 / Recall 0.6860 / Specificity 0.4887 / F1 0.3707 / Pearson r 0.2151 | 记账：冻结 pipeline 读数未被污染；但同报告引用的 3f=0.9993 无效 |
| 6 | 同目录 `01-requirements.md` | 220（块）/验收阈值表 | 「覆盖率 < 50% 且 AUC < 0.65 → `mmpsy feature compatibility insufficient` + 回归均值主导」 | 「回归均值主导」这一判据解释无效 |
| 7 | 同目录 `02-architecture.md` | 174（块）/Step 7 | 「gap > 0: 填充特征有微弱贡献 / gap ≈ 0: 几乎无贡献 / **gap < 0: 填充特征引入噪声 (回归均值效应)**」 | **污染结论的定义源头**：设计阶段就把 `gap<0` 硬编码解释为「填充噪声」，未设「gap 两侧不可比」或「特征可能泄漏」的检查 ⇒ 整段设计无效 |
| 8 | `archive/2026-09/planning/v1.25-mmpsy-lite-risk-model/01-requirements.md` | 23（块）/开放问题表 | 「❌ 跨人群泛化未解决 | mmpsy AUC 0.6249, Specificity 0.4887, 特征覆盖率 50% | 不是校准问题，是建模失配」 | 记账：0.6249 未被污染；但「不是校准问题，是建模失配」的排他性归因过强（当时未排除特征泄漏可能） |
| 9 | `archive/2026-09/planning/v1.25-mmpsy-lite-risk-model/06-learnings.md` | 30（块）/经验段 | 「12 个 v1.23 特征中，6 个可由 PHQ-9/GAD-7 线性派生（stress_level, anxiety 等）…继续做特征映射已无意义」 | 把「可从量表派生」记为**能力**，漏判「从标签所用那份量表派生 = 泄漏」；正确结论应是「mmpsy 与 PHQ-9 标签域重叠，不构成独立外部验证集」 |
| 10 | `docs/金丝雀期间其他事情.md` | 774（块）/772（原文） | 「融合模态 F1=0.9808, AUC=0.9993 异常高 — 原因是 `phq9_score` 列是 `phq9_binary` 标签的来源」 | **无需更正**（已当场发现并修复，表格 `泄露 ✅ none`）。加注记是因为它是 L4 **同类问题的第二次独立出现** ⇒ 立项 T3 闸门的依据 |

合计 **10 处**（提示词点名 4 处 + 本轮自查补 6 处，其中 2 处是「定义源头」设计文档）。

### 1.3 go/no-go 影响记账（不翻案，交用户裁决）

| 决策 | 依据读数 | 是否被污染 | 说明 |
|---|---|---|---|
| v1.24 mmpsy 外部验证「no-go / 约束通过」 | AUC 0.6249 | **否** | 冻结 pipeline 跨域推理，未吃到泄漏红利；实测复现路径一致 |
| v1.24 报告中「3 特征判别力 0.9993」 | AUC 0.9993 | **是** | 同义反复 |
| v1.24「插补噪声/回归均值」解释 | gap −0.3744 | **是** | 跨口径之差 |
| v1.25「停止 mmpsy 特征映射」 | 覆盖率 50% + AUC 0.6249 | **否** | 结论方向不变（且 §1.2 #9 给出了更强的正确理由：标签域重叠） |
| v1.26 threshold sweep「go」 | selected_threshold=0.40 | **是（L3，见 §4）** | 阈值在测试集上选 |

**结论：未发现任何 go/no-go 决策因污染结论而被推翻。** 被污染的恰是两个「支持继续」的
乐观读数（0.9993）与一个「解释性」结论（回归均值），而它们都没有改变决策方向
（决策方向本就由未污染的 0.6249 决定，且方向是「不通过」）。
本轮只记账上报，不重估任何历史决策。

---

## 二、T2：代码护栏（防复发，不动历史输出）

文件：`backend/scripts/modeling/v1_24/01_build_mmpsy_features.py`（**归档历史脚本**）。

**为何不改历史输出**：该脚本的产物 `mmpsy_structured_features.csv` 及其衍生的
v1.24 全部读数是历史快照。改数值 = 篡改历史；且它会与 §1.2 的更正块失去对应关系。
所以只做「加护栏 + 加横幅 + 默认安全化 + 保留显式复现开关」。

改动：

1. **模块 docstring 加⛔横幅**：`⛔ 禁止用于模型评估（含标签同源派生特征）`，
   并说明 `stress_level` 由 `phq9` 派生 ⇒ 与 `phq9_binary` 标签同源。
2. **显式登记表**：
   - `LABEL_DERIVED_FEATURES = {"stress_level": ("phq9_score", "PHQ-9 总分（标签同源，AUC=1.0）"), "anxiety": ("gad7", "GAD-7 总分（另一量表，非同源标签，泄漏弱但须声明）")}`
   - `PROXY_DERIVED_FEATURES = {...}`（其余派生特征）
   - 依据提示词要求：`anxiety` 派生自 GAD-7，非标签源 ⇒ 判「泄漏弱」但在映射报告中显式声明「派生自另一量表（GAD-7），非同源标签」。
3. **默认安全化**：`derive_stress` / `derive_anxiety` 保留原函数（历史复现用），
   但 `main()` 默认路径把 `stress_level` 置 `NaN`、`stress_level_source="unavailable"`；
   只有显式 `--allow-historical-repro` 才走历史派生路径。
4. **映射报告显式声明**：`feature_mapping.md` 新增段，逐特征标注
   `derived_from_label_source` / `derived_from_other_scale` / `unavailable`，
   并对 `stress_level` 给出「mmpsy 无真实 stress 字段 ⇒ 该特征在 mmpsy 不可得」。

---

## 三、T3：目标泄漏升为提交期闸门

`backend/tests/test_p2_38_leakage_audit_guard.py` 新增 `TestG5TargetLeakageGuard`（7 条）：

| 用例 | 断言 |
|---|---|
| `test_builder_file_exists` | 护栏脚本存在 |
| `test_every_label_derived_feature_is_declared` | 每个从标签源派生的特征都必须在 `LABEL_DERIVED_FEATURES` 登记（AST 扫描赋值左值 vs 登记表，差集必须为空） |
| `test_stress_level_is_declared_as_label_derived` | `stress_level` 登记为标签同源（`phq9_score`） |
| `test_anxiety_is_declared_as_proxy` | `anxiety` 登记为代理派生（`gad7`，另一量表，非同源标签） |
| `test_default_path_does_not_emit_stress` | **AST 分支断言**：只有 `if repro:` 分支允许派生，else 分支必须把 `stress_level_source` 置 `unavailable`（且必须存在 `--allow-historical-repro` 开关） |
| `test_prohibition_banner_present` | 模块 docstring 含「⛔ 禁止用于模型评估」横幅 |
| `test_detector_catches_new_label_derived_feature` | 合成帧里新造的标签派生特征必须被 `detect_target_leakage()` 判为泄漏（闸门自身有效性） |

反向对照（防「只会报警」的假闸门）在 `TestG2TargetLeakageDetection` 中：
`test_pure_noise_passes`（纯噪声特征不得被判泄漏）。
合计 `TestG5` 7 条；全文件 `G1(2)+G2(4)+G4(3)+G5(7)=16 passed`。

**为何不能依赖真实数据文件**：`mmpsy_structured_features.csv` 与 `mmpsy_scores.csv`
均**未入库**（CI 干净 checkout 不存在）。所以 T3 用「AST 源码断言 + 合成数据」，
真实数据断言（`test_real_mmpsy_stress_is_leaky`）带 `pytest.skip` 保护（CI 上跳过，已记账）。

### 真实变异（红 → 还原绿）

| 变异 | 内容 | 强度自审 | 结果 |
|---|---|---|---|
| M6 | 新增 `stealth_leak = phq9_score * 0.37`，**不登记**进 `LABEL_DERIVED_FEATURES` | 强：真值空间翻转（差集 ∅→非∅） | **红 1/1**，且只红 `test_every_label_derived_feature_is_declared`（精准，非无脑报警） |
| M7 | `if repro:` 改为 `if True:`（默认路径改回派生） | 强：默认产出形态翻转 | **红 1/1** |
| M8 | 从 `LABEL_DERIVED_FEATURES` 删掉 `stress_level` 登记 | 强：登记集合翻转 | **红 2/2** |

**M7 首次假绿的教训（已修复）**：初版用**文本断言**
（`'stress_level_source"] = "unavailable"' in src`），只要字符串还在源码里就绿，
与它在哪个分支无关 ⇒ 变异后仍 16 passed（假绿）。改为 **AST 分支断言**后立即红 1/1。
这是「断言必须钉结构、不能钉字面量」的第五次实锤。

还原后：`16 passed`；含既有棘轮复跑 `15 passed`（守卫 16 + 全称注释 + 桶计数，部分类级选择）。

---

## 四、T4：§七 未验证项逐条裁定（不再挂账）

### 4.1 阈值/权重挑优 5 处（人工读码，逐条给结论 + 行号）

| # | 位置 | 裁定 | 依据（行号） |
|---|---|---|---|
| 1 | `scripts/m5_calibration_thresholds.py`（`best_threshold`×2） | **L3 成立** | L677 `y_for_threshold = pred["y_test"]`；L681 `scan_thresholds(..., best_prob_test)`；函数内 L379/L387 两个赋值分支都在该 test 集上选。**例外**：L674 `use_cross_calibrate` 分支（生理模态 5-fold 交叉校准）用 `y_val`，干净。影响面：校准研究报告中的 per-modality 阈值 |
| 2 | `scripts/eval_model.py`（`best_threshold`×1） | **L3 不成立** | L292 `threshold = metrics.get("best_threshold_info", ...)` —— 阈值来自训练期 metrics，非本脚本选；**源头** `scripts/ml_training/train_tabular.py:232 find_best_threshold(best_model, X_val, y_val)` 在 **val** 上选、L233-234 再用于 test ⇒ 正确做法。L147 的 `0.46` 只是 PR 图标注常量；L158-169 `plot_threshold_optimization` 在 `X_val` 上且仅可视化 |
| 3 | `backend/scripts/modeling/v1_26/01_threshold_sweep.py` | **L3 成立** | L71-72 单次 `train_test_split` 丢弃训练集只留 test；L78 `model.predict_proba(X_test_scaled)`；L91-119 在 `y_test` 上扫全部阈值；L126 `selected_t = best_recall_constrained_t`；L145-148 写 `selected_threshold_config.json`（含 `go_decision`）。**下游无代码消费**（仅 archive 文档引用）⇒ 无生产路径传播 |
| 4 | `scripts/optimize_fusion_weights.py`（`best_f1`×2） | **L3 成立**（性质：规则权重，非统计模型） | L4/L9 docstring 自述 "Searches for optimal fusion weights on **83 test scenarios**"；L33 默认 `datasets/fusion/fusion_test_scenarios_v2.json`；L250-291 `grid_search_weights` 在该测试场景集上按 `metrics["f1"]` 选优 |
| 5 | `backend/scripts/modeling/v1_24/04_train_adapter.py:214-221`（提示词点名） | **L2+L3 均成立** | `idxmax` 在 `full_df` 上选参，最终 `validate` 又在同一 `full_df` 上执行 ⇒ 选参与验证同集 |

### 4.2 本轮新查（清单外，一并裁定）

| 位置 | 裁定 | 依据 |
|---|---|---|
| `backend/scripts/modeling/v1_27/04_retrain_bilingual_text_groupwise.py:294` | **干净（正面确认）** | L266-267 `_scan_thresholds(zh_grouped["label"].values, group_oof)` —— 阈值在**组级 OOF** 预测上选，英文 holdout 未参与选参。记账：L289 最终模型在全量中文上评估属已知乐观偏差，不属 L3 |
| `v1_26/selected_threshold_config.json` 下游 | 无代码消费 | 全仓 grep 仅命中 archive 文档 |

### 4.3 `aligned_features.csv` 56 个完全重复行：**可忽略**（定量结论，不留预估）

| 量 | 实测值 |
|---|---|
| 总行数 | 28552 |
| 完全重复组 / 涉及行数 | **56 组 / 112 行** |
| 占比 | **0.392%**（提示词预估 0.2%，实测为 1.96 倍，仍同量级） |
| 重复组内标签冲突 | **0 / 56** |
| 随机划分 vs 按重复行分组划分 | AUC 0.9167 → 0.9124；F1 0.8619 → 0.8573 |
| **Δ（泄漏虚高）** | **ΔAUC +0.0043 / ΔF1 +0.0046** |

判据：Δ < 0.005 且重复占比 < 0.5% ⇒ **判定「可忽略」**，不构成对 v1.23 划分结论的威胁。
（口径：LR + class_weight=balanced + liblinear，seed=42，test_size=0.2。）

---

## 五、产物与读数

| 产物 | 内容 |
|---|---|
| `docs/ML_LEAKAGE_REMEDIATION.md` | 本文件 |
| `backend/scripts/modeling/v1_24/01_build_mmpsy_features.py` | T2 护栏（横幅 + 登记表 + 默认安全化 + 复现开关） |
| `backend/tests/test_p2_38_leakage_audit_guard.py` | T3 新增 `TestG5TargetLeakageCommitGate`（7 条；反向对照 1 条在 G2） |
| `backend/tests/tools/mutate_p2_38_round14_result.log` | M6/M7/M8 变异日志（M7 含假绿→修复记录） |

**测试读数**：守卫 `16 passed`；既有棘轮复跑 `15 passed`。
**CI读数**：见提交记录（`total_count` 实数由收工 commit message 报出）。

## 六、未验证记账（不乐观推断）

1. `aligned_features.csv` 重复行结论基于**单次划分 + LR**；未跑多 seed 方差分析。
   判据 Δ<0.005 下认为不影响结论方向。
2. T3 的真实数据断言在 CI 上 **skip**（数据文件未入库）；本机已实测通过。
   若将来数据入库，需去掉 skip 并在 CI 复核。
3. §4.1 #1（m5）与 #4（optimize_fusion_weights）的 L3 **只做了裁定，未做整改**——
   它们是历史研究脚本，按「先检测后整改」分批，整改不进本轮。
4. `eval_model.py` 的阈值来源已追到 `train_tabular.py`（val 选阈值，干净）；
   但**未追** `RandomizedSearchCV` 的调参是否在 test 上做过（metrics.json 由 RandomizedSearchCV 产出）。
5. 未执行方向 A / 方向 C；未碰 10 处编号特性 TODO；未重开 #35；未改现役生产预测主路径。

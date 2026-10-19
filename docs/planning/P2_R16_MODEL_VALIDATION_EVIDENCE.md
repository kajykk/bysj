# ROUND_16 模型验证证据补强（临床报告技术类差距落地）

> 日期：2026-10-19 ｜ 上游：`docs/planning/P2_R15_CLINICAL_READINESS.md` §6.2（P1 差距清单）
> 边界声明：本轮**只做技术类差距**（P1-1/2/3/4/8 + P2-1）。P0 的组织/法律项
> （主体资格、产品定性 甲/乙/丙）**不在本轮**——需决策者拍板，先于任何技术动作；
> 不改产品声明档位。新增能力一律走离线/评估层，接入生产主路径需单独评审。

## 〇、开工前置核验（先实测，不信转引）

| 项 | 实测 |
|---|---|
| HEAD vs origin/main | 均为 `c349a89`（一致） |
| `git diff \| wc -c` | 0（git status 的 M 为 CRLF/stat 缓存假报；3 个 M 文件逐一 `git hash-object` 判定：degradation.py SAME-BYTES 纯假 M，另两个为本轮真实编辑） |
| 未跟踪文件 | 7 个，均为前序轮次运行时产物（pool*.json / leak_delta*.json / verify result json），按惯例不入库 |
| 既有能力边界（不重复造轮子） | `model_validation.py` 已有 Wilson/Bootstrap CI、Brier、calibration curve、`compute_fairness_metrics`(min_group_size=30)、报告生成 ⇒ **缺 DCA/净获益、缺 ECE**（T1 缺口实锤）；`risk_thresholds.py` 低分直返 0 级、有 `NonFiniteRiskScoreError` 先例（T4 缺口实锤）；`confidence.py` 是现成 SSOT 范式（T5 可复用） |

## 一、T1 校准与临床决策效用（P1-1）

### 做法
`backend/app/ml/model_validation.py` 新增：
- `decision_curve_analysis()`：Vickers & Elkin 2006 口径净获益 NB(t)=TP/n−FP/n·pt(t)，
  pt(t)=t/(1−t)；逐阈值对比「全治」线 NB=π−(1−π)·pt 与「全不治」线 NB=0；
  汇总判据限定在**固定临床区间 (0.1, 0.4)**（SSOT，不可由调用方搬动凑门槛）。
- `compute_ece()`：等宽分箱 ECE=Σ(n_b/n)·|acc_b−conf_b|，给校准误差单一汇总数。
- `generate_clinical_validation_report()` 增加 `decision_curve` + `ece`（**仅二分类**，多类不强套）。
- `compute_fairness_metrics()` 补齐差距读数（见 T3）。

### 门槛（先定）
临床合理阈值区间 (0.1–0.4) 内，模型净获益**逐阈值 ≥ 全治线且 ≥ 全不治线**；
达不到则如实报 `model_dominates_extremes_in_range=False`，不得靠移区间凑。

### 读数（探针实测，非引用）

**A. 结构化模型 v1.23_external_lr —— 外部留出集（n=4318, 阳性率 0.5813）**

| 指标 | 读数 |
|---|---|
| AUROC | 0.9131 |
| Brier | 0.1152 |
| **ECE** | **0.0139**（校准良好） |
| DCA 区间内模型 NB 最小值 | 0.4505（全治线区间 −0.17~0.53） |
| **门槛判定** | **`model_dominates_extremes_in_range=true`（达标）** |

**B. 双语文本模型 —— groupwise OOF 真口径（n=8379, 阳性率 0.2163）**

| 指标 | 读数 |
|---|---|
| AUROC | 0.8437（与 v1.27 metrics JSON 一致，复现成功） |
| Brier | 0.128 |
| **ECE** | **0.0855**（中等） |
| NB@t=0.3 | 模型 0.0806 vs 全治 −0.1196 ⇒ 模型占优 |
| NB@t=0.5 | 模型 0.0523 vs 全治 −0.5675 |
| **门槛判定** | **`model_dominates_extremes_in_range=true`（达标）** |

两条证据链均**不用调阈值**即压过两条极端线。对照组（随机分数）在区间内
`model_dominates_treat_all_in_range=false`（反空转见证，证明判据可分辨）。

## 二、T2 多模态融合增量消融（P1-2）

### 做法
新建 `backend/app/ml/fusion_ablation.py`：同队列 ΔAUROC（配对 bootstrap CI）、
NRI/IDI、分组 K 折（组不跨折）、阈值只在训练折选、provenance 强制落档
（source/in_sample/grouping 必填意识）。

### 阴性结论（如实立项）
1. **自然队列增量无法量化**：三个模态的训练队列**受试者不相交**——结构化
   （PHQ-9 条目，`data/processed/v1_23_external/`）、文本（中文语料+reddit）、
   生理（WESAD 风格 13 维可穿戴，第三方队列）。同一患者不存在三模态测量
   ⇒ 共同队列不存在 ⇒ ΔAUROC 无合法估计对象。**不伪造共同队列、不 cherry-pick 子集。**
2. **设计样本 fixture 消融（in-sample 警示）**：`datasets/fusion/fusion_test_scenarios_v2.json`
   49 条中仅 21 条三模态齐全（其余为单/双模态缺失处理场景，按同队列纪律剔除）。
   结果：structured AUROC=1.00、physiological 0.963、text 0.8287、fusion 1.00；
   **ΔAUROC(fusion−structured)=0.000, CI=[0.000, 0.000] 覆盖 0 ⇒ 无显著增量**；
   NRI=IDI=−0.2043（连续指标下融合反而略逊）。
3. **该读数受构造限制**：fixture 的标签由场景名（structured_{low,mid,high}）定义，
   结构化臂必然天花板——**Δ=0 是构造的必然，不能外推自然队列**。且融合权重
   （optimize_fusion_weights.py）历史上正是在**同一文件**上 in-sample 挑选的，
   provenance 已置 `in_sample=true`。

**立项**：融合增量维持"实验"级证据（`MODEL_REGISTRY.md` §3 标注不变）；
需要真实共同队列（同一被试的结构+文本+生理测量）才能给出点估计+CI。

## 三、T3 公平性评估与缓解（P1-3）

**评估**（assessment，已落报告）：`compute_fairness_metrics` 在 gender 分组外部留出集
（female n=1854 / male n=2464，min_group_size=30 保护内）：

| 差距读数 | 值 |
|---|---|
| tpr_gap（机会均等差） | 0.0208 |
| fpr_gap | 0.0093 |
| fnr_gap（=tpr_gap，恒等式） | 0.0208 |
| equalized_odds_gap | 0.0208 |
| ppv_gap | 0.0097 |

**缓解**（mitigation，与评估**分账**，状态一律 `recommended_not_enabled`）：
新建 `backend/app/ml/fairness_mitigation.py`：
- `suggest_group_thresholds`：按组 Youden 最优阈值。实测两组均选 0.6（收敛）⇒
  组阈值相对统一阈值（0.6）无增益，代价读数全零——**建议在此评估集上无收益**。
- `suggest_sample_reweights`：Kamiran & Calders 重加权（female 1.165 / male 0.876），
  注明仅对重训有效，当前基线模型不适用。
- 两条路径都带 cost 块（只报改善不报代价=无效建议）。

## 四、T4 漏报安全设计（P1-4）

缺口实证：`score_to_level` 是**纯分数**函数——总分低 ⇒ 0 级 ⇒ 呈现为"无风险/免复核"，
与 P0-3 修复的"NaN→无风险"同属最危险失效方向。生产已有两条路径各自内联合成过
该逻辑（predict.py 的 text 与 mmpsy-lite 路径：危机命中⇒risk_level=4），但没有
可复用、可断言的统一安全网。

修复：`backend/app/core/risk_thresholds.py` 新增
`apply_false_negative_safety_net(risk_level, *, crisis_signal, review_signal)`：
- 危机信号 ⇒ 等级下限 4（critical）+ 强制人工复核；
- 其他复核信号 ⇒ 等级下限 1（mild）+ 强制人工复核；
- 两者皆无 ⇒ 原样返回（行为不变）。
等级下限取值与既有 crisis_override 行为一致，**不是新引入的临床判定**。

⚠️ **未接入生产主路径**（本轮边界：新增能力走离线/评估层；当前两条生产危机路径
行为与本安全网 crisis 分支等价，接入是行为保持的等价重构，需单独评审）。

**可执行断言**（TestT4 类，含一次真实变异 M5——安全网中性化 ⇒ 断言红）：
`apply_false_negative_safety_net(score_to_level(2.0)=0, crisis_signal=True)` ⇒ (≥4, True)。

## 五、T5 阈值口径 SSOT（P1-8）

### 缺陷实锤（探针复现，非代码走读）
重跑 v1_27 groupwise OOF（同折同种子同规格）得到逐样本概率后：

| 口径 | 混淆矩阵 (tn/fp/fn/tp) | 与 JSON headline 一致性 |
|---|---|---|
| JSON headline（标称 threshold=0.3） | 6031/536/838/974 | — |
| **重算 @ t=0.5** | **6031/536/838/974** | **精确一致** |
| 重算 @ t=0.3 | 4773/1794/368/1444 | 不一致 |

即 headline 块是**按硬编码 p>=0.5 算的**（`_evaluate` 源码第 98 行实锤），
而顶层 `threshold: 0.3` 与生产 `settings.text_bilingual_decision_threshold=0.30`
是**另一个口径**。旁证：0.3 处 recall=0.7969≥0.75 恰为 rationale 所称"约束集
F1 最高者"的选择点——**选的是 0.3、报的是 0.5**，任何按 0.3 解读 headline 的
结论都会错。

### 修复（历史数字一律不动，只追加口径登记）
1. 新建 SSOT：`backend/app/core/ml_decision_thresholds.py`（confidence.py 范式：
   docstring 口径对照表 + 常量）。
2. `config.py` 默认值改为引用 SSOT 常量（行为不变，环境变量仍可覆盖）。
3. v1_27 脚本：`_evaluate` 阈值具名常量化 `HEADLINE_EVAL_THRESHOLD=0.5`
   （AST 断言钉死不得回退裸字面量），`main()` 输出 `headline_eval_threshold`
   与 `threshold_governance` 块。
4. metrics JSON **追加式**补丁（`git diff` 验证纯新增、历史值逐键比对不变）：
   新增 `headline_eval_threshold`、`threshold_governance`（含 annotation）。
5. 清除死副本：`fusion_engine.CONFIDENCE_THRESHOLDS`（全仓无生产消费方，
   与 confidence.py SSOT 语义重叠）删除，其测试改钉 SSOT 常量。
6. `model_validation._DEFAULT_CLINICAL_RANGE` 改引 SSOT。

### 口径对照表（单一事实源）

| 口径 | 值 | SSOT 位置 | 消费方 |
|---|---|---|---|
| 双语文本决策阈值（概率） | 0.30 | ml_decision_thresholds.py ↔ Settings | predict.py 文本路径 |
| headline 历史计算阈值 | 0.50 | ml_decision_thresholds.py ↔ metrics JSON `headline_eval_threshold` | 仅历史评估读数 |
| DCA 临床区间 | 0.10–0.40 | ml_decision_thresholds.py → model_validation | DCA 汇总 |
| 置信回退阈值 | 0.50 | confidence.py `LOW_CONFIDENCE_THRESHOLD` | risk_thresholds.should_fallback |
| 模态质量分档 | 0.80 / 0.50 | confidence.py `MODALITY_*` | fusion 质量分档 |
| 风险分级 cutoff（0–100 分） | 18/35/55/72 | models/v1.23_external_lr/threshold_config.json | 结构化分级 |

### 一致性闸门（TestT5 类）
- settings == SSOT 常量；
- 脚本常量 == SSOT（AST 钉值）；
- `_evaluate` 默认阈值必须是具名常量（AST: ast.Name）；
- **metrics JSON 自洽**：headline (recall/precision/f1) == sweep 表 `headline_eval_threshold` 行；
- JSON `threshold` == settings == SSOT（三方锁）；
- **反空转见证**：headline 三元组必须与决策阈值行**不同**（否则两口径不可分辨，闸门失效）；
- fusion_engine 不得再定义 CONFIDENCE_THRESHOLDS（AST）；
- predict.py 必须经 settings 读阈值（AST 属性访问）。

## 六、T6 TRIPOD+AI 对照导出（P2-1，可选项已做）

`backend/tests/tools/export_tripod_ai_appendix.py` → `docs/planning/P2_R16_TRIPOD_AI_APPENDIX.json`。
27 项（含子项 50 条）逐条对照，状态分账：**evidence 28 / partial 13 / missing 3 / na 6**；
ROUND_16 本轮补齐项（3c 健康不平等、12e DCA/ECE、14 公平性、15 阈值、23 性能CI）标注
`improved_by=ROUND_16`。缺位如实留档：摘要(item 2)、伦理(item 17)、PPI(item 19)。

## 七、闸门与变异证据

- 闸门文件：`backend/tests/test_p2_40_model_validation_round16.py`（**38 条全绿**）。
- 变异套件：`backend/tests/tools/mutate_p2_40_round16.py` + `mutate_p2_40_round16_result.log`
  ——9 个真实变异（JSON 口径漂移/脚本常量漂移/死副本复活/SSOT 单边漂移/安全网中性化/
  DCA 公式符号翻转/fnr_gap 移除/ΔCI 判据恒真/分组泄漏校验旁路），
  逐个 RED-OK、还原后 GREEN-OK。残留判定用**变异标志串计数**（全部为 0）——
  本轮文件本就含合法改动，hash 对比 HEAD 会全量显差，故不用 hash-object；
  标志串加换行前缀防「注释内引用」误报（首版曾误报 2 处，均在此列）。
- 探针（读数来源，非引用）：`probe_p2_40_round16_struct.py` + `probe_p2_40_round16_text.py`
  （OOF 概率与标签的 .npy 落盘供复核；按仓库 `*.npy` 忽略惯例不入库，
  跑探针即可本地重生成，digest/读数已写入随行 result.json）。

## 七之二、全量回归与本轮台账连带修正

- 本地全量（无 cov、`--tb=line -rfE`，完整日志 `full_run_r16_final.log`）：
  **6 failed / 7368 passed / 20 skipped / 7 errors**。失败全部为**本地环境性**，
  逐一隔离复跑证实与本轮改动无关：
  - `test_importlinter_config`：本机 PATH 无 `lint-imports` CLI（历史已知环境红）；
    契约静态核验通过——本轮新依赖边均为 `app.ml → app.core`（允许方向）与
    `app.core.config → app.core.ml_decision_thresholds`（core→core），
    不触犯 `forbidden: app.core → app.ml/app.services` 契约。
  - `test_model_registry_atomicity` / `test_scheduler_artifact_cleanup`×3 /
    `test_p2_11::batch25_declined`：隔离复跑全绿；全量上下文中的根因有日志铁证——
    本地 shim 的 safe-delete guard 对 basetemp 内 `os.replace` 抛
    `[WinError 5] 拒绝访问`（`model_registry_v2.py:402 Failed to persist` 链），
    属本地沙箱文件操作拦截，CI 无此组件。
  - 7 个 error 落点（collect-only 有序清单 + 进度点反推）：perf_p2_001×3、
    sec_p2_003×1、upload_security_p1×1、validation_engine×2——同批文件隔离
    复跑 125 passed。
  - 带 `--cov` 的本地全量必在 `cov.combine()` 的 `os.remove` 触发同一 guard
    （SystemExit(1) → INTERNALERROR，FAILURES 段来不及打印）——本地既有限制，
    权威读数以 CI 为准。
- **本轮真实引入的一处候选池变化及处置**：`fusion_ablation.py` bootstrap 循环的
  `except Exception: continue` 被 #35 扫描器计为未接线 X 候选（X 116→117）。
  实测判决为**运行期不可达**：NaN/inf 输入会让 `roc_auc_score` 抛 ValueError，
  但同函数未包裹的同参数调用（原 106/107 行）必先抛出，循环内该 except 永远
  走不到；且吞掉 bootstrap 样本会腐蚀 CI（`n_bootstrap_valid` 静默降权）。
  按「不可达路径不接线更危险」纪律**移除该 except**（退化重采样的 pre-check
  计数保留），X 桶回到 116、总数 334 不变。
- **台账连带同步**（棘轮要求，历史快照不动、只追加）：
  - `docs/P2_11_ROUND11_AUDIT.md` 追加 ROUND_16 段：`other_raise 335→345`
    （+10 = model_validation 4 + fusion_ablation 4 + fairness_mitigation 2，
    均为入参校验 ValueError，响亮失败语义）；HTTPException=211 / ServiceError=37 不变。
  - batch36 location 钉漂移：`app/ml/model_validation.py` 的
    `_bootstrap_auc_ci_with_count` except 由 122 行移到 135 行（文件头 +13 行），
    `test_p2_11_round11.py` 与 `tests/tools/verify_p2_35_batch36_candidates.py`
    共四处钉同步 122→135，行为断言不变。修复后 `test_p2_11_round11.py` 233 passed。

## 八、未决与边界记账

1. **P0 组织/法律项未碰**（主体资格、甲/乙/丙定性）——需决策者拍板，先于任何技术动作。
2. T2 融合增量：**阴性立项**（队列不相交 + fixture 构造天花板 + 权重 in-sample）；
   真实增量待共同队列数据。
3. T3 缓解：两条路径均"建议、未启用"；组阈值实测无收益（两组都选 0.6）。
4. v1.23 结构化模型的 Youden 最优阈值实测为 0.6，与生产决策阈值 0.30/0.50 均不同——
   属评估口径参考值，**不推动生产改阈值**（改阈值需临床论证+单独评审）。
5. T6 missing 3 项（摘要/伦理/PPI）为文档治理项，留待注册资料阶段。
6. sklearn 版本兼容（S-02 `_fill_dtype` 补丁）在探针中复用生产同一手法，
    未改动生产加载器。

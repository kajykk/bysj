# P2_56 · ROUND_29 审计：D-R26-1（P0）修复——生产 scaler 错配致 Recall 0.60

> 状态：起点 HEAD `94e3f9d`（ROUND_28 闭环，论文素材包 + 数字闸门）。
> 范围：修复 ROUND_26 立案的 P0 缺陷 D-R26-1（artifact scaler 与仓内任何数据版本不匹配，
> 生产路径 test recall 仅 0.6000），并为防复发建立永久闸门。
> 全部读数为 2026-10-22 ~ 2026-10-23 实测；数据集（`datasets/`）与 artifact
> （`backend/models/artifacts/`）均不在版本库 ⇒ 涉及它们的步骤只在数据机器执行并如实记账。

## 〇、结论先行

- **缺陷属实且已修复**：修复前生产 Recall 0.6000（TP=33 / FP=0 / FN=22 / TN=102）；
  修复后同一 n=157 测试集、同一阈值 0.5 下 **Recall 0.8727**（TP=48 / FP=14 /
  FN=7 / TN=88）、F1 0.8205、ROC AUC 0.9451。
- **这是修标准化缺陷，不是模型变强**：修复后 AUC 由 0.9884 **下降**到 0.9451——
  没有任何能力读数变好；变回来的是「生产链路与训练一致」（co-consistent by construction）。
- **没有为迁就测试集调参**：超参数沿用 `metrics.json` 记录值；修复后单切分 Recall
  低于修复前旧权重的诊断读数 0.9455，本文不追这个数（测试集上调参即泄漏）。
- **防复发闸门已落地并被变异证明有效**：`tests/test_p2_56_round29_scaler_consistency.py`
  三层判据；修复前真实缺陷状态下两层分别变红，变异 6/6 臂红 + 末臂 GREEN。

## 一、缺陷链（T0 前置实测）

| 事实 | 实测 | 出处 |
|---|---|---|
| 部署 scaler 的 sleep_quality 均值 | 5.4279（**超出 1-5 量表**） | `scaler.json.broken_round29` |
| 部署 scaler 的 overall_activity 均值 | 460098.75（域内但错配约 5 倍；重拟合值 109771.125） | 同上 |
| 标准化后 z 分数 | 多列 abs(mean_z) > 1（sleep_quality -1.00、steps -1.41） | ROUND_26 诊断 |
| 生产路径 test recall | 0.6000（每 10 个阳性漏约 4 个） | 已提交 csv 逐行连续性核对 |

**域检盲区**（三层闸门的设计动机）：overall_activity 错配 5 倍仍落在合法域
[0, 1.44e8] 内 ⇒ 任何只查「参数是否物理合理」的检查都抓不到它；必须配
**可复现性主闸门**（同切分同管线重拟合对拍）。

## 二、T1 Provenance 诊断：为什么走路径 B（端到端重训）

旧权重 + 重拟合 scaler 在本数据上的重复 CV（5 折 × 3 次，与 ROUND_26 同折）：
recall **0.8729±0.0342**，且 train/val/test = 0.8924/0.7925/0.9455 强依赖切分
⇒ 旧权重与当前数据**不稳健兼容**，只换 scaler 不够 ⇒ 判定**路径 B**。

## 三、T2 修复：路径 B 端到端重训

脚本（已入库）：`backend/scripts/modeling/eval/v1_29/04_round29_retrain_physiological.py`。
八条纪律写在脚本 docstring：train-only 拟合 / co-consistent by construction /
固定 seed 42 / 超参照抄禁调参 / 坏工件字节级存档 / 如实报告 / 熔断线 / 原子替换。

- **管线**：`DataCleaner.fit(train 719)` → `build_features` → `SimpleStandardScaler.fit(X_train)`
  → MLP 在经该 scaler 变换的 X_train 上训练；推理链加载同一套工件。
- **超参**（全部沿用旧记录，未调）：epochs 120 / batch 32 / lr 0.001 / weight_decay 0.005 /
  patience 15 / hidden [128,64,32,16] / dropout 0.2 / BN 开；best_epoch=27，
  best_val_f1=0.8302。
- **熔断线**：FLOOR_RECALL=FLOOR_F1=0.5（低于修复前 0.60，只防训练崩坏，不是目标值）。
- **确定性**：`--check-determinism` 同 seed 两跑，model/scaler/cleaner/feature_names
  **逐字节一致**，metrics.json 除时间戳全等。
- **float32 量化修正**：训练反向传播把权重提升到 float64，而 artifact 交付形态是
  float32 ⇒ 不量化则内存/磁盘分数差 ~1e-8（实测 7.96e-08）。训练后显式量化回
  float32，生产复载校验 max|diff| = **0.0e+00**。
- **连续性**：修复前分数与已提交 csv 生产列逐行相等（atol=1e-12），json rec point
  0.6（1e-6）⇒ 「修复前口径」锚定在已提交产物上，不是口头数。
- **原子替换**：staging 同卷 `os.replace` + `clear_artifact_cache()` + 生产路径复载断言；
  坏工件先存档（`*.broken_round29`，存档前以 `.sha256` 侧车证明字节未被篡改）。

**前后对照（同一 test 157 行，均无任何 fit 涉及 test）**：

| 口径 | Acc | Prec | Recall | F1 | AUC | AUPRC | CM TP/FP/FN/TN |
|---|---|---|---|---|---|---|---|
| 修复前（存档工件） | 0.8599 | 1.0000 | 0.6000 | 0.7500 | 0.9884 | 0.9847 | 33 / 0 / 22 / 102 |
| 修复后（新工件） | 0.8662 | 0.7742 | **0.8727** | 0.8205 | 0.9451 | 0.8919 | 48 / 14 / 7 / 88 |

新管线重复 CV（5 折 × 3 次，与 T1 同折）：recall **0.8784±0.0415**（min 0.8197，
max 0.9667）/ f1 0.8768±0.0303 / AUC 0.9597±0.0148。

**工件 sha256（当前生产目录）**：cleaner `234c69ff…` / scaler `310ee08d…` /
feature_names `1d96dca6…` / model `d2b0b805…` / metrics `20f30678…`；
`test_predictions.csv` `1853a250…`。

## 四、T3 防复发闸门（`tests/test_p2_56_round29_scaler_consistency.py`，5 例）

三层判据，各有分工：

1. **第一层（主闸门 · 可复现性）**：同切分（seed=42，719/153/157）、同管线在 train 719 行上
   重拟合 scaler，断言部署 `scaler.json` 逐特征 `allclose(rtol=1e-3, atol=1e-4)`。
   修复后实测 max|mean diff| = max|scale diff| = **0.000e+00**。
2. **第二层（域合理性）**：13 特征硬合法域表（物理界/公式 clip/量表界，附来源）+
   scale>0 + Popoviciu 上界（有界变量 std ≤ (b−a)/2）。
3. **结构层**：len==13、顺序对 `feature_names.json`、`n_features_in`==13。
4. 完整性：`.sha256` 侧车相符；修复落地：部署 ≠ 修复前存档。

**修复前真实缺陷状态下的效力**（把存档 scaler 放回生产目录实测）：第一层 RED
（max|mean diff| = 3.503e+05，overall_activity 460098.75 vs 重拟合 109771.125）；
第二层 RED（sleep_quality mean 5.4279 越界 + scale 2.5924 超 Popoviciu 上界 2.0 +
activity_intensity scale 13888 超 5000）。

**变异见证**（`backend/tests/tools/mutate_p2_56_round29.py`，日志
`mutate_p2_56_round29_result.log`；每臂字节快照 try/finally 还原、变异后重生成侧车、
子进程全新 pytest 防模块缓存假绿；变异字面量 = 存档真实坏值，启动时交叉核对）：

| 臂 | 变异 | 结果 |
|---|---|---|
| M1 | overall_activity mean→460098.75（域内错配 5 倍） | RED（仅第一层——域检盲区被主闸门兜底） |
| M2 | sleep_quality mean→5.4279（越量表界） | RED（第二层 + 第一层） |
| M3 | sleep_quality scale→2.5924（超 Popoviciu 2.0） | RED（第二层 + 第一层） |
| M4 | n_features_in→12（mean/scale 仍 13 项） | RED（结构层 + 第一层） |
| M5 | 交换 heart_rate/systolic_bp 两个 mean（两值均域内合法） | RED（**仅第一层**——第二层对此完全失明，盲区论证的直接证据） |
| M6 | 修复前存档放回生产目录 | RED（TestFixIsInPlace + 另两层） |
| M7 | 全部还原 | **GREEN**；字节级还原校验通过 |

合计 6/6 臂被拦截，末臂 GREEN ⇒ 前面的红不是环境性假红。

## 五、T4 重评估与论文回填

- **01 全量重跑**（`v1_29/01_reproducible_eval.py`）：新 csv + json + 报告；
  `--report-only` 与全量运行产物**逐字节一致**（ROUND_27 硬闸门复验通过）。
  csv 中 `y_score_refit_scaler` 与 `y_score` **157/157 行逐位相等**——co-consistency
  的工件级证明；该列语义由「缺陷定位」改为「一致性证明」（01 的 docstring/报告/json
  note 已同步，含「1029 行 670/359」笔误修正为 359 阳性/670 阴性）。
- **论文回填**（四份文档 + 台账）：
  - C-01~C-06 更新为修复后读数；C-07~C-09 由「缺陷定位诊断列」改为「一致性证明列」
    （与生产相等即证据）；
  - 修复前 0.60 / 0.7500 / 0.9884 / TP=33 与旧权重诊断 0.9455 / 0.9369 / 0.9841
    全部标注「历史口径/不可比」，只以拒绝性表述出现；
  - 明确写入「这是修标准化缺陷不是模型变强」（AUC 下降为证）与「修复后 0.8727 低于
    修复前诊断 0.9455，不追数」的如实记账；
  - `docs/model-evaluation/README.md` 与 `docs/P2_53_ROUND26_…AUDIT.md` 加 ROUND_29
    取代声明，旧数字不再以现行口径出现。
- **数字闸门**：`verify_thesis_numbers.py` returncode **0**（36 条登记 + 章节主表/
  迁移表/混淆矩阵/诊断表 + 黑名单 + 引用纪律全部一致）。

## 六、回归与规模

- 回归组（p2_10 棘轮 / p2_11 / p2_38 / p2_46 / p2_49 / p2_55 / p2_56）：
  **293 passed, 0 failed**（143s）。本机 CLI shim 在 passed 汇总后拦截 teardown 的
  临时目录 rmtree（`SystemExit: 1`），系环境层行为，CI 无此 shim。
- 后端用例收集数：7,552 → **7,557**（`pytest --collect-only -q` 实测；增量全部来自
  p2_56 五例）。README 已同步。
- 闸门只读承诺未动：`verify_thesis_numbers.py` 本轮零改动（新数字不撞黑名单 token，
  FINE_NUM 纪律由文档侧标记满足）——**没有为了过闸门而改判据**。

## 七、如实记账（未验证与边界）

1. **CI 干净 checkout 一层都跑不到**：数据集与 `physiological_optimized/` 的三个模型工件
   （`model.json` / `scaler.json` / `feature_names.json`）均不在版本库 ⇒ `test_p2_56`
   因 `skipif` 在 CI 整模块 skip。数据机器上的实测（max diff = 0.000e+00、变异 6/6）
   仅记录在本文件，**CI 侧无证据**；该闸门已显式降级为 data-machine-only gate
   （B4 完成：模块级 `pytestmark` 的 `reason` 声明，CI 跳过原因可见、不静默）。
2. **变异脚本依赖数据机器**：需要数据集 + 修复前存档 + 生产工件三者俱在，启动时逐项断言，
   缺失即拒绝运行（不产出没有依据的「绿」）。
3. **registry 未动**（B-02 边界）：`model_registry.py` 的 `artifact_metadata`
   （hidden_dims [64,32,16] / dropout 0.3）与实际权重仍不符，本轮只在新 metrics.json
   里记录真实超参，不在 registry 侧改数。
4. **`/health/startup` Sentry 误记 ok**（第二十七批发现）仍开放，与论文数字无关，
   台账 LIMITATIONS §4.3 继续记账。
5. 修复后 metrics.json 记录真实切分 719/153/157（旧记录 719/171/139 不可复现，
   ROUND_26 三重证据），旧值随存档工件保留。

## 八、产物清单

- 新增：`backend/tests/test_p2_56_round29_scaler_consistency.py`（5 例）、
  `backend/tests/tools/mutate_p2_56_round29.py` + `_result.log`、
  `backend/scripts/modeling/eval/v1_29/04_round29_retrain_physiological.py`（T2 已入库）、
  本审计文档。
- 更新：`v1_29/01_reproducible_eval.py`（docstring/报告模板/json note）、
  `docs/thesis/` 四份、`docs/model-evaluation/README.md`、
  `docs/P2_53_ROUND26_EVAL_REPRODUCIBILITY_AUDIT.md`（取代声明）、`README.md`（用例数）。
- 已跟踪、本轮重生成并随提交入库：`backend/models/artifacts/physiological_optimized/
  test_predictions.csv`(+`.sha256`)、`docs/model-evaluation/physio_v2_current_data_eval.json`、
  `docs/model-evaluation/PHYSIO_V2_EVAL_REPORT.md`（01 单命令产物；
  `--report-only` 逐字节复现）。生产 artifact 五件与 `*.broken_round29` 存档四件
  不在版本库（ROUND_26 分层），只在数据机器。

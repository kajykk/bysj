# 模型评估证据（论文/答辩用图与数据）

生成方式均为仓库真实数据 + 真实产物实测，可复现（见各节命令）。

## 1. 生理 MLP v2 测试集不确定性

> **⚠️ ROUND_26（2026-10-23）复核：本节 1 的旧证据已不可复现，且 AUC 口径已作废。**
>
> - **139 行测试集无法重建**：仓内唯一的切分函数 `stratified_split`（两个历史版本逐行相同）
>   在 depresjon 1029 行上恒给 **719/153/157**，不是 `metrics.json` 记录的 719/171/139；
>   且 artifact 的 `scaler.json` 统计量与仓内三份生理数据都对不上
>   （sleep_quality 均值 5.43 超出 1-5 量表）。原训练脚本从未入库。
>   ⇒ 旧 json 与 png 里的 139 行数字属于一份**不在仓内的数据版本**，只能作为历史记录引用，
>   **不得**用于对外材料、也不得与新评估混用。
> - **新证据**：`physio_v2_current_data_eval.json` + `PHYSIO_V2_EVAL_REPORT.md`
>   （由 `backend/scripts/modeling/eval/v1_29/01_reproducible_eval.py` 生成，
>   逐样本分数落盘 `test_predictions.csv` + `.sha256`，一条命令可复算）。
>   新口径点估计 = 全样本统计量；所有 CI（含 AUC）= bootstrap 分位（B=10000, seed=42）。
> - **口径差异**：旧 `f1.point=0.8527` 是 bootstrap 均值，全样本名义值是 0.8541667
>   （= `metrics.json`）；旧 AUC CI 的 Hanley-McNeil 近似已由 bootstrap 取代。
> - **当前数据上的实测**（n=157，生产路径）：F1 0.7500 **[0.6410, 0.8434]**，
>   AUC 0.9884 **[0.9699, 0.9990]**，Recall 0.6000 **[0.4717, 0.7292]** —— Recall 低是
>   artifact scaler 与当前数据版本不配套所致（重拟合 scaler 的对照口径 F1 0.9369，非生产），
>   缺陷登记见 `docs/P2_53_ROUND26_EVAL_REPRODUCIBILITY_AUDIT.md`。
> - **ROUND_27（2026-10-23）口径修正与更强门槛**：上面这些 CI 端点相对 ROUND_26
>   首次公布的值（F1 [0.6383, 0.8431]、AUC [0.9694, 0.9990]、Recall [0.4687, 0.7288]）
>   有变化，**根因是行序不是精度**：ROUND_26 用 split 的 `tei` 乱序算 bootstrap，
>   而 csv 按 `row_index` 升序落盘 ⇒ 复算路径抽样落点不同。ROUND_27 起
>   （a）csv 存 float64 往返精度（`.17g`）；（b）指标与 CI 一律按**落盘行序**计算；
>   （c）`--report-only` **同时重写 JSON + 报告**。验收口径改为
>   **「提交版 sha == 单命令产物 sha」**：对已提交的 `test_predictions.csv` 跑
>   `--report-only`，重写出的 JSON 与报告必须与仓库里的提交版**逐字节相等**。
>   点估计与混淆矩阵不受影响（TP=33/FP=0/FN=22/TN=102）。

- `physio_v2_test_ci.json`：测试集 n=139 的 95% CI。
  阈值指标（Acc/Prec/Rec/F1）为非参数 bootstrap（B=10000，seed=42），
  混淆对由 `backend/models/artifacts/physiological_optimized/metrics.json`
  反推（TP=41, FP=3, FN=11, TN=84，已用 acc/prec/rec 交叉验证）；
  AUC 因未持久化逐样本分数，采用 Hanley-McNeil SE（保守近似，已标注方法）。
  **→ 已被取代，仅存历史（见上方说明）。**
- `physio_v2_test_ci.png`：论文第 4 章直接引用。关键口径：
  F1=0.854 [0.769, 0.923]，Recall=0.788 [0.672, 0.896] ——
  区间宽是 n=139 的必然结果，答辩时主动说明，不宣称高精度。
  **→ 该图基于不可复现的 139 行切分，论文引用前须改用新证据并说明差异。**

## 2. 融合权重敏感性

- `fusion_weight_sensitivity.csv/.png`：结构化权重 0.35–0.75 扫描
  （文本/生理按 0.30/0.15 比例缩放，关闭置信度加权以隔离权重效应）。
- 结论：模态一致时 spread≈1.6（鲁棒）；模态冲突时 spread=19.3，
  即**权重只在模态打架时重要** —— 这正是保留人工复核与危机词优先规则的依据。

## 3. 论文数字台账与校验闸门（ROUND_28 · P2-55）

本目录的 json/csv 是「论文可引用数字」的唯一合法来源；ROUND_28 起另有一层文档台账：

- `docs/thesis/CLAIMS_LEDGER.md`：36 条登记（C-01~C-22 指标、S-01~S-08 数据集规模、
  X-01~X-06 敏感性），每条带来源产物路径 + 复算命令 + 「可否进论文」判定；
  另立禁用黑名单 B-01~B-05（n=139 旧口径、registry 0.9530 第三套数字、
  bootstrap 均值误记 0.8527 等），命中即视为学术不诚信。
- `docs/thesis/RESULTS_CHAPTER.md`：可直接进论文的结果章节（实验设置 / 域内主表 /
  P0 缺陷披露 / 跨数据集迁移 / 敏感性 / 可复现性 / 结论），样本量写每节首行。
- `docs/thesis/REVIEWER_QA.md`、`docs/thesis/LIMITATIONS.md`：审稿问答与局限性，
  所有数字带台账编号。
- 机器闸门：`backend/scripts/modeling/eval/verify_thesis_numbers.py`（只读，CI 每次提交跑），
  从**已提交** csv/json 独立复算台账每一行并与四份文档逐一比对（容差 = 展示精度），
  任一漂移即红；测试接入 `backend/tests/test_p2_55_round28_thesis_numbers.py`，
  变异见证 `backend/tests/tools/mutate_p2_55_round28_result.log`（8 臂 RED + 末臂 GREEN）。

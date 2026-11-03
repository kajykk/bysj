# 模型评估证据（论文/答辩用图与数据）

生成方式均为仓库真实数据 + 真实产物实测，可复现（见各节命令）。

## 1. 生理 MLP v2 测试集不确定性

> **⚠️ 2026-11-02 来源审计（优先于本节所有数字）：训练表的 5/7 原始生理特征由真实队列
> 标签驱动合成，`phq9_score` 也是标签副本；仅 `steps`/`exercise_minutes` 来自真实
> actigraphy。仅真实列 5 折 OOF AUC 0.6443，合成列 0.9898，当前测试 AUC 0.9451
> 落在合成列可解释范围内。本节及 `PHYSIO_V2_EVAL_REPORT.md` 的 F1/AUC 只能作
> 生产管线一致性/回归读数，不得作为真实生理信号性能或人群外推证据。
> 审计与复现：`PHYSIO_DATA_PROVENANCE_AUDIT.md`。**
>
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
> - **当前数据上的实测**（n=157，生产路径，**ROUND_29 修复 D-R26-1 后**）：
>   F1 0.8205 **[0.7387, 0.8889]**，AUC 0.9451 **[0.9064, 0.9768]**，
>   Recall 0.8727 **[0.7800, 0.9531]**（混淆矩阵 TP=48 / FP=14 / FN=7 / TN=88）。
>   修复前同口径为 F1 0.7500 / AUC 0.9884 / Recall 0.6000
>   （TP=33 / FP=0 / FN=22 / TN=102，历史口径，不可比）——病根是 artifact scaler
>   与数据版本不配套；ROUND_29 按路径 B 端到端重训（co-consistent by construction），
>   修复记录与防复发闸门见 `docs/P2_56_ROUND29_SCALER_FIX_AUDIT.md`。
>   **这是修标准化缺陷，不是模型变强**：修复后 AUC 由 0.9884 降至 0.9451。
> - **ROUND_27（2026-10-23）口径修正与更强门槛**：上面这些 CI 端点相对 ROUND_26
>   首次公布的值（F1 [0.6383, 0.8431]、AUC [0.9694, 0.9990]、Recall [0.4687, 0.7288]）
>   有变化，**根因是行序不是精度**：ROUND_26 用 split 的 `tei` 乱序算 bootstrap，
>   而 csv 按 `row_index` 升序落盘 ⇒ 复算路径抽样落点不同。ROUND_27 起
>   （a）csv 存 float64 往返精度（`.17g`）；（b）指标与 CI 一律按**落盘行序**计算；
>   （c）`--report-only` **同时重写 JSON + 报告**。验收口径改为
>   **「提交版 sha == 单命令产物 sha」**：对已提交的 `test_predictions.csv` 跑
>   `--report-only`，重写出的 JSON 与报告必须与仓库里的提交版**逐字节相等**
>   （ROUND_29 重训后已复验通过）。ROUND_27 当时点估计与混淆矩阵不受影响
>   （彼时 TP=33/FP=0/FN=22/TN=102）；ROUND_29 更换 artifact 后混淆矩阵随重训
>   变为 TP=48 / FP=14 / FN=7 / TN=88。

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

- `docs/thesis/CLAIMS_LEDGER.md`：55 条登记（C-01~C-38 指标、S-01~S-08 数据集规模、
  X-01~X-09 敏感性），每条带来源产物路径 + 复算命令 + 「可否进论文」判定；
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

## 4. 人群适用范围与证据矩阵（ROUND_46 · Phase 0）

- `POPULATION_EVIDENCE_MATRIX.md`：四类运行时推理单元（结构化/文本/生理/融合）的
  登记人群、验证队列、证据等级、迁移风险与弃权口径。结论：现有证据只支持
  「登记人群内的筛查辅助 + 人工复核」，不支持「全人群通用」声明。
- `MODEL_CARD_TEMPLATE.md`：人群感知模型卡模板，以及当前四个单元的已回填卡片；
  字段与运行时注册表 `backend/app/core/population_scope.py` 一一对应。
- 运行时披露：预测与模型状态响应新增 `population_scope`，四个单元当前均为
  `automated_decision_allowed=false`、`abstention_recommended=true`；
  前端在结构化/文本/融合结果处展示 `PopulationScopeNotice.vue`。
- 本阶段不更换模型工件、不改阈值、不重新训练；跨人群能力需在 Phase 1
  用外部成人/临床队列离线评估后再登记。
- **ROUND_47（2026-11-02）NHANES 2017–2018 迁移压力测试**：生产生理 MLP 原样用于
  n=5,068 名有标签成人，AUC 0.5459 [0.5163, 0.5754]，平均预测 0.471 vs 实际阳性率 0.091，
  校准斜率 0.2114、ECE 0.3804。因标签（临床分组 vs PHQ-9≥10）、特征来源（5/7 为标签驱动
  合成）与采集协议同时变化，该读数**只能作压力测试**，不升级生理单元证据等级，也不能与
  0.9451 并列。见 `NHANES_TRANSPORT_STRESS.md`。
- **ROUND_48（2026-11-02）真实 actigraphy 分组基线**：回到 Depresjon 原始分钟级数据，
  55 受试者 / 1,029 完整日，按受试者分组。主口径（受试者均值 + LOSO，4 真实特征）
  AUC 0.6454 [0.4861, 0.7983]；多日聚合次口径 0.7620 ± 0.0093，置换 p=0.002。
  同队列回顾性，**不是外部验证、不是生产替换**；见 `REAL_ACTIGRAPHY_BASELINE.md`。
- **ROUND_49（2026-11-02）真实基线稳健性与佩戴混杂**：18 个规范网格的受试者级 LOSO AUC
  0.5855–0.7364（中位 0.6569），0.6454 不是稳健点估计；仅用零活动日/活动分钟/记录天数
  代理的 LOSO AUC 0.7921，病例平均 15.6 个完整日 vs 对照 20.9。排除全零日最多的三名
  受试者后主口径仍为 0.640–0.655、代理模型 0.775–0.792。仍为同队列回顾性评估，
  不升级证据等级；见 `REAL_BASELINE_ROBUSTNESS.md`。
- **ROUND_50（2026-11-02）多日聚合口径的规范稳健性**：固定 ROUND_48 的日级分组 CV，
  变动自相关缺失处理（zero/mean/drop）× 日纳入（all/nonzero/min14）共 9 个规范。
  预注册 `day__zero__all` 精确复现 **0.7620 ± 0.0093**，但 9 规范受试者级 AUC 为
  **0.6565–0.7620**（中位 0.7091），0.7620 恰为网格最大值；日级口径在 9/9 配对中高于
  受试者级 LOSO（+0.0187 到 +0.0789），但差值随规范变化；校准斜率 3.23–4.28。
  仍为同队列回顾性，不升级证据等级；见 `REAL_BASELINE_PROTOCOL_ROBUSTNESS.md`。

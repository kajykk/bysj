# P2_59 · ROUND_33 审计：P1 概率校准与决策曲线分析（Brier / ECE / MCE / calibration slope / DCA）

> 状态：工作树产物（ROUND_30~32 已提交之后）在本轮完成度核验后一次性入库。
> 范围：对已落盘的逐样本预测 csv 做概率级校准分析与决策曲线，接入台账
> C-26 ~ C-33 与论文素材包，并为数字闸门补独立复算路径。
> 除特别标注外，全部读数为 2026-10-24 实测；涉及数据集与 artifact 的步骤只在
> 数据机器执行（`datasets/` 与 `backend/models/artifacts/` 不在版本库）。

## 〇、结论先行

- **主口径读数**（文本 groupwise OOF，n=8379 / 1277 组）：Brier **0.1280**
  [0.1184, 0.1376]、ECE **0.0855** [0.0710, 0.1069]、MCE 0.1435、校准斜率
  **1.3466**、截距 −0.3541；DCA 上模型净获益在阈值 **[0.03, 0.99]** 优于
  「全员干预」、在 [0.01, 0.68] 优于「不干预」。
- **斜率 1.3466 > 1 的方向是「偏保守（欠自信）」而非过自信**：预测概率在 logit
  尺度上离散度不足、被压向中间；与固定阈值 0.5 下 Recall 0.5375 [C-24] 自洽。
  过自信的反例在本轮同一批数据里就有：生理模型跨 Kaggle 后斜率跌到 0.1356
  [C-30]，与 AUC 0.5120 [C-12]（CI 覆盖 0.5，随机水平）互为印证。
- **引用边界先于指标**：只有 `text_groupwise_oof` 是可引用泛化口径；
  `physio_current_split`（n=157）为次级、引用处必须同句标注 n；两个 transfer
  单元（文本×OOD strict n=2523、生理×Kaggle n=10000）是压力测试，禁作外迁。
  本轮用它们的读数论证「不可跨数据集引用」本身，不用来论证能力。
- **没有做校准后处理、没有扫描阈值**：重拟合需要独立留出集（n=157 与已用尽的
  OOF 均不满足），阈值下调只给方向性结论（§4ter.1），未实测收益。

## 一、产物清单（全部入库）

| 文件 | 角色 |
|---|---|
| `backend/scripts/modeling/eval/v1_33/calibration_lib.py` | 纯函数库（Brier/ECE/MCE/slope/DCA/bootstrap） |
| `backend/scripts/modeling/eval/v1_33/calibration_analysis.py` | 四单元 CLI，只读逐样本 csv，同写 json + 报告 |
| `backend/scripts/modeling/eval/v1_33/calibration_analysis.json` | 四单元全量读数（含 99 点 DCA 曲线与可靠性表） |
| `docs/model-evaluation/CALIBRATION_REPORT.md` | 人读报告（脚本生成，非手写） |
| `backend/tests/test_p2_59_round33_calibration.py` | 16 例（手算对拍 / 边界 / 工件一致性 / 闸门联动） |
| `backend/tests/tools/mutate_round33_calibration.py` + `_result.log` | 变异见证 7/7 RED + 恢复绿 |
| `backend/tests/tools/mutate_round33_pathfix.py` + `_result.log` | 修复提交的新闸门变异见证（RED→GREEN，见 §六） |
| `backend/scripts/modeling/eval/verify_thesis_numbers.py` | +254：校准/DCA 独立复算（另一套算法路径） |
| `docs/thesis/` 四份 + `CHANGELOG.md` + `README.md` | 台账 C-26~C-33、§4ter、§3bis、Q9/Q10、索引行 |

**纪律**：点估计与 bootstrap CI 共用同一套实现（避免「CI 一种算法、点估计另一种」
的隐性不一致）；不跑模型、不读 `metrics.json` / registry 旧值，全部从已落盘的
逐样本预测 csv 复算；CI 为分位法，文本按 group 重采样（与 v1_30 同源同 seed 42）。

## 二、读数（与 `calibration_analysis.json` 逐位一致）

| 单元 | role | n | Brier | ECE | MCE | slope | 台账 |
|---|---|---|---|---|---|---|---|
| `text_groupwise_oof` | citable | 8379 | 0.1280 [0.1184, 0.1376] | 0.0855 [0.0710, 0.1069] | 0.1435 | 1.3466 | C-26/27/28 |
| `physio_current_split` | citable_secondary | 157 | 0.1408 [0.1252, 0.1573] | 0.2160 [0.1815, 0.2647] | 0.3225 | 3.7602 | C-29 |
| `text_ood_strict` | stress_only | 2523 | 0.0281 [0.0264, 0.0289] | 0.1363 [0.1325, 0.1401] | 0.4355 | 5.9873 | C-31 |
| `physio_kaggle` | stress_only | 10000 | 0.2761 [0.2729, 0.2793] | 0.1535 [0.1452, 0.1642] | 0.2412 | 0.1356 | C-30 |

DCA 阈值区间（模型净获益 > 基线）：主口径优于 treat_all = [0.03, 0.99]、优于
treat_none = [0.01, 0.68]（另 0.89 单点）；代表点 t=0.50 模型 0.0523 [C-32]
vs treat_all −0.5675，t=0.05 模型 0.1763 [C-33] vs 0.1750（低阈值端增量很薄）。

**斜率/截距无 CI、DCA 无净获益 CI**：前者每次 bootstrap 要重跑一次优化、成本
不成比例且解释价值在方向；后者同。C-28 的 CI 单元格为「—」，结论只作方向性判断。

## 三、闸门与测试

- **数字闸门**：`verify_thesis_numbers.py` 对校准读数用**另一套算法路径**独立
  复算——ECE 显式区间遍历（非 searchsorted）、slope 用 Nelder-Mead 直接最小化
  logloss（非 Newton/IRLS）——与库实现互为对拍。**returncode 0**（台账 47 条）。
- **测试** `test_p2_59_round33_calibration.py` **16 例**：手算 Brier 对拍、
  ECE 四组边界（完美校准 / 单箱失校准 / 分箱边界 / 按计数加权）、slope 方向与
  确定性、DCA 公式（含 FP>0 阈值）与开区间拒绝、概率越界强制、json 的
  units/roles/n↔csv/sha/阳性率/DCA 阈值区间、slope 无 CI、闸门联动。实跑
  **16 passed**。
- **确定性实测**（本轮复跑验证，非转抄）：`calibration_analysis.py` 连跑两次，
  json 与报告均**字节级一致**（sha256 `454de14b…`）。

## 四、变异见证（7/7 RED + 恢复绿）

| 臂 | 变异 | 杀死它的判据 |
|---|---|---|
| M1 | Brier 翻成 L1 | 手算对拍 |
| M2 | ECE 去样本数加权 | 单箱失校准 + 按计数加权两例 |
| M3 | ECE 距离量符号翻转 | 手算对拍 |
| M4 | DCA 假阳性惩罚符号翻转 | **FP>0 阈值**（见下） |
| M5 | DCA 阈值放开到闭区间 | 开区间拒绝例 |
| M6 | 拆掉概率越界检查 | ValueError 断言 |
| M7 | transfer 单元口径升级为 citable | role 字段断言 |

**M4 暴露过的测试覆盖缺陷（已修复并留档）**：初版 DCA 公式测试所有样例 FP=0，
把减号翻成加号不改变任何读数 ⇒ 变异存活。修复：补 FP>0 的阈值用例
（t=0.05 全预测为正、t=0.2 部分为正、单样本 FP 惩罚项），翻转后读数变化被
断言抓住。该记录写在 `test_dca_net_benefit_formula` docstring，变异脚本对
M4 显式指定该节点。基线 GREEN + 7 臂 RED + 还原 sha 一致，日志
`mutate_round33_calibration_result.log`。

## 五、回归与同步（本轮实测）

- 回归组：p2_59（16）+ p2_55 + p2_56 + p2_57 + p2_58 + p2_10（注释棘轮）
  **44 passed, 0 failed**。
- `pytest --collect-only -q` 实数 **7,582**；README 逐轮校准行：
  ROUND_29 记录 7,557 → 本轮 7,582，差额 25 = 本轮 p2_59 16 例 + ROUND_30/31
  的 p2_57/p2_58 共 9 例（该两轮未在 README 登记增量，此处一并归属）。
- ROUND_00 全轮审计文档加后记：其「ROUND_33 工作区未提交、冲突以 HEAD
  （716677d）为准」的基线声明，自本轮提交后由本审计文档接续。

## 六、CI 抓出的缺陷与修复（ROUND_33 修复提交）

**缺陷**：首版提交（09564c5）的 `calibration_analysis.json` 的 4 个 `source` 字段
在 Windows 上生成（`str(Path)` ⇒ 反斜杠分隔符）。本地 Windows 跑测试全绿，但
CI 干净 Linux checkout 下 `REPO / "backend\\scripts\\..."` 把整串当文件名 ⇒
4 个 calib 单元全部误报「source 不存在」，`backend-coverage` **3 failed /
7224 passed**（p2_55 闸门测试 + p2_59 两例）。首轮监视该 job 被并发 push
取消（cancelled≠失败），重跑后才暴露——**教训：本机全绿不等于交付形态成立，
路径分隔符是交付形态的一部分**。

**修复**（最小变更，数值零漂移）：

| 文件 | 改动 |
|---|---|
| `v1_33/calibration_analysis.py` | 4 处 `str(p.relative_to(...))` → `.as_posix()` |
| `v1_33/calibration_analysis.json` | 重生成：4 个 source 行改 posix（仅此 4 行，4/4） |
| `verify_thesis_numbers.py` | `REPO / u["source"]` → 归一化 `replace("\\", "/")`（防御旧产物） |
| `test_p2_59_...py` | 新增形态钉断 `assert "\\" not in u["source"]` + 同样归一化 |

**验证**：json 与报告的数值 diff 为空（仅 4 行路径）；p2_59+p2_55 **20 passed**；
闸门 **rc=0**；新闸门真实变异（生成端退回 `str()`）**RED 于形态断言**→字节级
还原→GREEN，日志 `mutate_round33_pathfix_result.log`。

**CI 结果**（修复提交 d93e23b，watch_ci.py 24m39s）：**10/10 success**——
backend-coverage 由 3 failed/7224 passed 转绿（三个失败点即本缺陷），其余 9 项
（contract-test / E2E Full Stack / frontend-coverage / coverage-summary / harness /
lighthouse / 双 Gitleaks / 部署窗口检查）全 success。跨平台路径缺陷至此闭环。

## 七、未验证记账

1. **全量测试套件未本地跑**（约 37 分钟），本轮只跑回归组 44 例 + collect 实数；
   权威验证由 CI 承担——修复提交 d93e23b 已 **10/10 success**（§六），该项关闭。
2. **DCA 净获益与斜率/截距无 CI**（理由见 §二）；阈值区间描述「在本批数据上
   成立」，不构成跨人群保证。
3. **校准后处理未做、阈值收益未实测**：只诊断不修复；「下调阈值能到多少」
   需要一次阈值扫描实验，本文未做也未声称。
4. `physio_current_split` 的校准读数受 n=157 限制（ECE CI 宽约 0.083），
   所有引用处同句标注 n，不作任何定量外推。

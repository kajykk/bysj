# ROUND_30 审计：文本模态跨被试真实泛化（分组 bootstrap CI）

> 状态：HEAD `26d9681` 之后。本轮把已存在的 groupwise 去泄漏评估升级为
> 论文可辩护的「真实效果」主结果：补**按用户分组**的 bootstrap CI、正式进台账、
> 进校验闸门、加测试。**不重训模型、不碰生理/结构化 artifact、不引外部数据。**

## 一、为什么做这一轮

用户诉求「在真正场景达到真正效果」，且手上只有公开数据 + 已训模型（无真实外部数据、
无明显候选）。诚实的可行路径：用**已有的 MMPsy 语料做「同人群、换被试」的真实泛化**——
按原始用户分组、组间不重叠的交叉验证，是无需任何外部资源就能拿到的、最诚实的泛化读数。

## 二、数据与协议（先于指标）

- 数据：MMPsy 派生中文语料，**8379 条、1277 个原始用户、阳性率 21.6%**。
- 协议：sibling-aware 分组去泄漏——同一学生的原文与全部增强副本（同义/回译）同组，
  `StratifiedGroupKFold`×5 每折重训同规格 TF-IDF+LR，held-out 组评估。
- OOF 逐样本：`backend/scripts/modeling/v1_27/groupwise_oof_predictions.csv`
  （sha256 `0dd48b4a…`，已入库）。

## 三、本轮新增：分组级 bootstrap CI

- 脚本：`backend/scripts/modeling/eval/v1_30/groupwise_ci.py`（只读 OOF，写 `groupwise_ci.json`）。
- **方法关键**：bootstrap **按 group 重采样**（抽 1277 组，非按行）——同组行相关，
  按行会低估区间。B=10000、seed=42。
- 产物：`groupwise_ci.json`（含 method、oof sha256、四指标 point+ci95）。
- 确定性：重跑该脚本产出内容一致（LF 归一后 sha `c40fa308…`）；Windows 工作区生成
  CRLF（38 处，raw sha `df926624…`），LF 归一后与提交件逐字节一致，非随机。

### 结果

| 指标 | 点估计 | 95% CI（按用户分组） |
|---|---|---|
| F1 | 0.5864 | [0.5307, 0.6381] |
| ROC AUC | 0.8437 | [0.8170, 0.8696] |
| Recall | 0.5375 | [0.4764, 0.5975] |
| Precision | 0.6450 | [0.5782, 0.7114] |

对照（随机划分/兄弟泄漏口径）：F1 0.9964 / AUC 0.9994 ⇒ **虚高 F1 −0.41 / AUC −0.156**。

## 四、范围与诚实边界（写进论文，不得外推）

1. 这是**同人群、换被试**的泛化，不是跨平台/跨人群；后者需真正外部数据（本文无）。
2. 模型有真实信号（AUC CI 下界 0.817 > 0.5；对比生理迁移 0.512=随机），但偏弱：
   阈值 0.5 下漏掉约 46% 阳性。
3. 定位为**辅助初筛 + 人工复核**，非自主筛查。

## 五、接线与闸门

- `CLAIMS_LEDGER.md`：C-22 升级带 CI；新增 C-23（AUC）/C-24（Recall）/C-25（Precision），
  均标「泛化口径」并带 OOF sha + 复算命令 + 分组 CI。
- `RESULTS_CHAPTER.md`：新增「4bis 跨被试真实泛化」节，含指标表（`（跨被试）` 后缀区分主表）、
  虚高幅度、范围声明。
- `verify_thesis_numbers.py` 扩展：
  - 新增 `recompute_groupwise_ci()`（与脚本同序列按组重采样）；
  - 台账 C-23~C-25 的 CI 单元格复算校验；
  - 章节 groupwise 跨被试表解析校验；
  - `groupwise_ci.json` 工件对拍（oof sha + 四项 point/ci95）。
- `test_p2_57_round30_groupwise_ci.py`：5 例钉「存在 + method 不退化 + oof sha 自洽 +
  计数一致 + 点估计与 eval json 一致 + 入库」。

## 六、变异见证（闸门真在复算，非自证）

翻改 OOF 中一行的 label ⇒ 闸门 **FAIL 27 处**（oof sha 不符 + F1/AUC 点估计与 CI 全部漂移）；
还原后 sha 回到 `0dd48b4a`，闸门 rc=0。见本轮运行记录。

## 七、回归与同步

- 受影响套件 `test_p2_55 + test_p2_57 + test_p2_10 + test_p2_11 + 泄漏守卫 + portfolio`：
  **279 passed**。
- `verify_thesis_numbers.py` returncode 0（台账 39 条…全部一致）。
- collect 总数 7557→**7562**（+5 用例）；README 已同步；该值不被闸门钉死（见
  `check_portfolio_numbers.py` 注释）。

## 八、边界（如实记账）

- 不重训模型（OOF 已无泄漏，直接复算 CI 即可）。
- 不引外部数据（那是需真实数据的 B 路径，本轮不做）。
- 不把 0.586 包装成「模型强」——它就是真实的、偏弱但有信号的跨被试水平。
- `.gitattributes` 新增 `backend/scripts/modeling/**/*.json eol=lf`（证据产物字节稳定）。
- 工作区大量既往脏文件（p2_40_r16_* 等测试残留）经 `git reset` 甄别，**未纳入本轮提交**。
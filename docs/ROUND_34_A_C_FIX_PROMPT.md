# ROUND_34 提示词：ROUND_00 审计的 A+C 修正（文档对齐 + 记账；B 另立）

> 背景：ROUND_00 全量复核（`docs/ROUND_00_ALL_ROUNDS_AUDIT.md`）结论：
> 致命级红项 0；论文主结果（39 条台账 + 四份文档）与已提交产物一致；
> 但存在 6 条文档-产物不一致（A 类）与若干记账缺口（C 类）。
> 本轮**只做 A+C**。**B 类（改测试/脚本 5 条）另立 ROUND_35**，理由是 B 会动
> `test_p2_*` 与 `groupwise_ci.py`、影响 CI 基线与泄漏守卫，必须单独一轮带完整 CI 复核。

---

## 〇、前置：脏工作树处置（**本轮第一件事，必须先做**）

当前工作树存在**未提交的 ROUND_33 在建改动**，且 A 要改的文件正被它占用：

```
M  docs/thesis/REVIEWER_QA.md        # ROUND_33 已加 Q9/Q10
M  docs/thesis/CLAIMS_LEDGER.md
M  docs/thesis/RESULTS_CHAPTER.md
M  docs/thesis/LIMITATIONS.md
M  backend/scripts/modeling/eval/verify_thesis_numbers.py
?? backend/scripts/modeling/eval/v1_33/ ...
?? backend/tests/test_p2_59_round33_calibration.py ...
````

**处置规则（三选一，按现状判定）**：

1. **若 ROUND_33 尚未提交**：先让 ROUND_33 完成并提交，再开本轮；
   或经用户同意后 `git stash -u` 暂存 ROUND_33 全部改动，在**干净 HEAD** 上做 A+C，
   做完 `git stash pop` 恢复。**不得**把 A+C 与 ROUND_33 混进同一提交。
2. **若 ROUND_33 已提交**：直接基于新 HEAD 做 A+C。
3. **任何情况下**：A 类修改若与 ROUND_33 改动的同一文件同一段冲突，**以 ROUND_33 的新内容为基准**
   叠加 A 的修正（例如 REVIEWER_QA 的 Q9/Q10 必须保留，只在文档他处改 35→39）。

**开工前留证**：`git rev-parse HEAD` + `git status --short` 贴进报告，证明本轮基线。

---

## 一、A 类修正（纯文档，6 条，逐条给出定位与目标）

> 纪律：每个数字改动后，`verify_thesis_numbers.py` 必须仍 rc=0；改文档数字是"使文档与产物一致"，
> 不是"改结论"。改完必须重跑闸门。

| 编号 | 文件 | 现状（错） | 改为（对） | 注意 |
|---|---|---|---|---|
| A1 | `docs/thesis/REVIEWER_QA.md` | 写「35 条」台账 | 「39 条」 | 保留 ROUND_33 新增的 Q9/Q10；只改这个数字 |
| A2 | `docs/P2_57_ROUND30_GROUPWISE_CI_AUDIT.md` | sha `B9E38E01…`（孤证） | `c40fa308…`，并注明"Windows 生成 CRLF，LF 归一后与提交件一致" | 真值以 `groupwise_ci.json` 旁或 `Get-FileHash` 实测为准 |
| A3 | `backend/tests/test_p2_55_round28_thesis_numbers.py` | docstring 写「36 条」 | 「39 条」 | 仅改 docstring，不动测试逻辑 |
| A4 | `docs/P2_56_ROUND29_SCALER_FIX_AUDIT.md` | 称「CI 侧只有工件层证据」 | 改为「CI 侧**无**证据：`test_p2_56` 因工件未入库在干净 checkout 整模块 skip」 | 如实记账，不夸大 |
| A5 | `docs/thesis/CLAIMS_LEDGER.md`（C-22 备注） | 0.9964/0.9994 无独立编号/产物路径；0.8860 易被误读矛盾 | C-22 备注补：泄露口径 0.9964/0.9994 的**产物路径 + 复算命令**；注明 `ML_LEAKAGE_AUDIT.md:172` 的 0.8860 是**不同协议**，非矛盾 | 不得新增可进论文的数字，仅补溯源与说明 |
| A6 | `docs/P2_09_ROUND9_AUDIT.md`、`docs/P2_10_ROUND10_AUDIT.md` | 引用 `scan_p2_09_*`/`scan_p2_10_*` 扫描器但未入库 | 在文档显式加「扫描器未入库，清单不可单命令复算，仅作历史记录」标注 | 不改历史结论，只标边界 |

---

## 二、C 类记账（1 条）

| 编号 | 位置 | 内容 |
|---|---|---|
| C1 | `docs/ROUND_00_ALL_ROUNDS_AUDIT.md`（补一节「编号与凭证说明」） | 注明：R20/R21 为**编号空洞**（无提交、无记录，非遗漏）；R31/R32 **无独立审计文档**，以 commit + 变异日志为凭证 |

---

## 三、B 类：本轮**不做**，只在报告里列为 ROUND_35 待办

（不在本轮改任何 `test_p2_*` / 脚本；仅登记）

- B1 `groupwise_ci.py:118` 加 `newline="\n"`（去 Windows CRLF 字节差）
- B2 `test_p2_47:702` 恒空断言 `touched & covered_models` 修正为有效断言
- B3 `test_p2_50:40-69` 前两例弃"自建 SQL"，改断言生产实现
- B4 `test_p2_56` 提供 CI 可用工件，或明确降级为 data-machine-only gate（并把 A4 的表述与之对齐）
- B5 `test_p2_58` 增加"EATD 数据未被 git 跟踪"的负向断言

---

## 四、验证与收尾

1. 改完 A+C 后：
   ```bash
   cd backend && .venv/Scripts/python.exe scripts/modeling/eval/verify_thesis_numbers.py
   ```
   必须 rc=0（REVIEWER_QA/CLAIMS_LEDGER 改动会被闸门的引用纪律检查覆盖）。
2. 跑 `test_p2_55`（确认 A3 改 docstring 后仍绿）：
   ```bash
   cd backend && .venv/Scripts/python.exe -m pytest tests/test_p2_55_round28_thesis_numbers.py -q
   ```
3. 单命令复核 A2 的 sha：`Get-FileHash backend/scripts/modeling/eval/v1_30/groupwise_ci.json -Algorithm SHA256`，
   与文档写入值一致（并记录 LF 归一说明）。
4. **不碰业务代码、不碰测试逻辑、不碰 ROUND_33 在建文件**（除 A 要求且按 §〇 规则合并的文字外）。
5. 提交（若在隔离树完成，先 `git stash pop` 再由用户决定提交时机）；提交信息注明
   `ROUND_34：ROUND_00 审计 A+C 文档对齐与记账（B 另立 ROUND_35）`。

---

## 五、铁律

- A 是"改文档使**文档=产物**"，**不是**改结论；任何数字改动必须被闸门复算背书。
- 不得把 ROUND_33 的未提交内容裹进本轮提交；两者必须可分离追溯。
- 不可复算的历史（R9/R10 扫描器、PHQ-9 682 行）只标注边界，**不假装修复**。
- 诚实优先：宁可写"CI 无证据"，也不拔高为"已覆盖"。
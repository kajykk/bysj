# ROUND_00 提示词：全 ROUND 审查与验证（独立复核，非转引）

> 状态：HEAD `716677d`（ROUND_32 之后）。本提示词**不引入任何新功能**，只做一件事：
> 把过去所有 ROUND 声称"已修复 / 已验证 / 已达成"的东西，用当前仓的产物和代码**重新证明一遍**，
> 把"文档说 A、产物是 B、代码是 C"的不一致全部挖出来。
> **铁律**：所有结论必须能由**已提交产物 + 一条命令**复算，禁止转引任何 ROUND 的汇报文字。

---

## 〇、先建立"审查清单"（事实先行，不凭记忆）

1. 枚举全部 ROUND：

   ```bash
   git log --oneline --all | grep -iE "P2-|ROUND_" | sort
   ```

   忽略纯 `rev_s*_bt*` / `p2_40_r16_bt*` 历史草稿目录（测试残留，见 §六）。

2. 枚举每轮的两类凭证：
   - **审计文档**：`docs/P2_*_ROUND*_AUDIT.md`、`docs/ROUND_*_PROMPT.md`
   - **机器凭证**：`backend/tests/test_p2_*.py`（当前 26 个，以 `ls` 实测为准）

3. 产出 `docs/ROUND_00_ALL_ROUNDS_AUDIT.md`，首节即一张表：
   `ROUND | commit | 审计文档 | 机器凭证 | 核心声明 | 可否一条命令复算(Y/N)`。
   **填不满的行 = 待查重点。**

---

## 一、每轮必须回答的五个问题（逐轮填表）

对每个 ROUND，**只依据仓库现有产物**回答：

| 问题 | 判据 |
|---|---|
| Q1 该轮声称的"修复/功能"是否真在代码里？ | `git grep` 定位；不存在的 = 幽灵声明 |
| Q2 该轮的机器凭证是否真在 CI 里跑？ | 能找到 `test_p2_XX_*.py` 且 `pytest --collect-only` 收集到 |
| Q3 该轮的核心数字/结论能否复算？ | 有产物路径 + 复算命令；否则记"不可复算" |
| Q4 该轮是否被后续轮推翻/替代？ | 看是否有 SUPERSEDED / 黑名单登记；若有，旧声明是否已标废弃 |
| Q5 该轮有无"自我验证"嫌疑？ | 测试仅断言"自己写的常量"而非真产物 = 自证，记红 |

---

## 二、硬性复核（这几项必须真跑，不能只读文档）

### H1 · 论文数字闸门（ROUND_28/29/30 的地基）

```bash
cd backend && .venv/Scripts/python.exe scripts/modeling/eval/verify_thesis_numbers.py
```

- 必须 rc=0；`--show` 打印的真值表要能对上台账。
- **变异见证**（反证它真在复算，绝不放过）：临时改 `groupwise_oof_predictions.csv` 一行的 label
  ⇒ 闸门必须红；还原 ⇒ 必须绿。**红/绿都记进报告。**

### H2 · 可复算评估（ROUND_26/27 的地基）

```bash
cd backend && .venv/Scripts/python.exe scripts/modeling/eval/v1_29/01_reproducible_eval.py --report-only
```

- 记录哪些产物能在**无原始数据集**的干净 checkout 复算、哪些不能（需 `datasets/`，如实记"需数据"）。
- 关键：验证"**提交产物 == 单命令产物**"——重跑产物与已入库产物逐字节比（sha256）。不一致 = 红。

### H3 · 泄漏守卫（ROUND_10 起）

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/test_p2_38_leakage_audit_guard.py -q
```

- 确认训练/评估入口计数（如"40 文件/88 入口"）与守卫基线一致；
  ROUND_30/31 新增的 `v1_30/`、`v1_31/` 脚本**不得**被计为训练划分入口（它们是 transform-only / 只读）。

### H4 · 每轮机器凭证逐条跑

```bash
cd backend && .venv/Scripts/python.exe -m pytest $(ls tests/test_p2_*.py | tr '\n' ' ') -q
```

- 全绿才继续。任一红 = 该轮回归失败，单独列红项。

### H5 · ROUND_30 groupwise CI 自洽（最新一轮，易被忽略）

```bash
cd backend && .venv/Scripts/python.exe scripts/modeling/eval/v1_30/groupwise_ci.py
```

- 重跑必须产出**逐字节相同**的 `groupwise_ci.json`；
  `oof_csv_sha256` 必须等于 `groupwise_oof_predictions.csv` 的**行尾归一（LF）** sha（CRLF 不限平台）；
  口径 F1 0.5864 [0.5307, 0.6381] / AUC 0.8437 [0.8170, 0.8696]。

### H6 · ROUND_31 外部测试脚手架未越界

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/test_p2_58_round31_eatd_scaffold.py -q
```

- 必须证明 `v1_31/*.py` **只 transform 不 fit/split**（AST 断言）；
  且 EATD 数据**不在库**（`data/external/eatd/` 未被 git 跟踪）。

---

## 三、文档一致性三角核对（陷阱最多的部分）

对 `RESULTS_CHAPTER.md` / `CLAIMS_LEDGER.md` / `REVIEWER_QA.md` / `LIMITATIONS.md` 四份文档：

1. **每个数字**都要能在台账找到编号，且台账该编号有"来源产物 + 复算命令"。无编号的数字 = 违规（B-05）。
2. **黑名单数字**（台账 §二 B-01~B-05：旧优化版 0.8542 / 0.9653、registry 0.9530 等）
   **不得**出现在结果语境；出现即红。
3. **LIMITATIONS / REVIEWER_QA 引用数字必须带台账编号**（闸门 `check_citation_discipline` 会查）。
4. 重点核对易漂移的几处：
   - 生理域内 **F1 0.8205** vs 历史 0.8542（黑名单 B-01）——文档若混用 = 红。
   - 生理迁移 **AUC 0.5120**（随机）——不得被说成"有效"。
   - 文本 OOD **0.9862** 必须明确标注为"同源泄漏"，不得作泛化。
   - groupwise **F1 0.5864** 必须注明"同人群换被试，非跨人群"。

---

## 四、跨轮"因果链"审查（最容易被单轮审计漏掉）

按时间顺序检查是否存在**后续轮推翻了前面轮的结论但前面轮文档没标注**：

- ROUND_26（评估可复算化）→ ROUND_27（G1 收口，提交产物==单命令）→ ROUND_28（数字台账）
  → ROUND_29（scaler 修复，D-R26-1）→ ROUND_30（groupwise CI）→ ROUND_31（EATD 脚手架）→ ROUND_32（前端）。
- 列出每一处"后轮修正前轮"的地方（如 ROUND_29 修 D-R26-1），
  确认**前轮文档/台账已正确标注为历史/已替代**（如 scaler.json 存档为 `.broken_round29`、B-01/B-03 黑名单）。

---

## 五、输出：`docs/ROUND_00_ALL_ROUNDS_AUDIT.md` 必备章节

1. **总览表**（§〇）：每轮一行，五问结论汇总。
2. **硬性复核结果**（§二 H1~H6）：每条 ✅/❌ + 实际命令 + 关键输出行（粘贴真实 stdout，不许转述）。
3. **红项清单**：按严重度排序（致命=数字与产物不符 / 高=脚本不可复算 / 中=文档缺标注 / 低=注释冗余）。
   每条给 `文件:行 + 证据 + 修复方向`。
4. **自证嫌疑清单**：哪些测试是"只断言自己常量"的弱测试。
5. **不可复算清单**：哪些 ROUND 的数字在当前仓无法一条命令重算
   （如 PHQ-9 682 行、敏感性 csv 生成脚本缺失），如实记账。
6. **结论**：一句话——"全部 ROUND 中有 N 轮完全可复核、M 轮部分可复核、K 轮存在文档-产物不一致"。

---

## 六、边界与铁律（违反即本审查失败）

- **只读为主**：本审查原则上不改业务代码；若要修，只在 §三发现的"文档数字与产物不符"处修文档使其与产物一致，
  或修产物并同步文档（两边都动），并重跑闸门。
- **禁止信任何 ROUND 汇报文字**：所有"已修复/已验证"都必须由当前代码/产物重新证明。
- **历史残留目录**（`backend/p2_40_r16_bt*`、`backend/rev_s*_bt*`、`*_tmp_*`）**不是**本轮修复对象，
  但要在报告里登记它们是否为脏文件（未入库则说明，已入库则评估是否该清理）。
- **区分"真外部数据"与"派生泄漏"**：任何被称为"外部/泛化"的数字，必须能证明其数据不在训练集（ROUND_27 教训）；
  证明不了的一律降级为"域内压力测试"。
- **诚实优先**：宁可报告"这一轮无法复算"，也不要用"看起来合理"替代实测。负结果 / 不可复算同样是合格产出。

---

## 七、收尾

- 跑完后回贴：①总览表 ②红项清单 ③结论一句话。
- 若闸门/回归全绿且无红项，明确写"**全部 ROUND 复核通过，无文档-产物不一致**"。
- 若有红项，给出最小修复清单（不擅自扩大范围），等确认后再动。
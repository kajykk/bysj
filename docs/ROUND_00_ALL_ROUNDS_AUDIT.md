# ROUND_00 · 全 ROUND 独立复核审计（HEAD `716677d`）

> 审计日期：2026-10-24。
> 审计对象：**已提交的 HEAD `716677d`（ROUND_32 之后）**，不信任任何 ROUND 汇报文字；
> 所有结论由当前仓的代码、已提交产物和实际命令重新证明。
>
> **审计基线说明**：工作区当时存在未提交的 ROUND_33（校准）改动（`verify_thesis_numbers.py`
> +254 行、`CLAIMS_LEDGER.md`/`RESULTS_CHAPTER.md`/`LIMITATIONS.md`/`REVIEWER_QA.md`
> 有增量、`backend/scripts/modeling/eval/v1_33/` 未跟踪，且会话期间仍在新增
> `test_p2_59_round33_calibration.py`）。为不触碰用户在建工作，H1/H2/H5 在
> `git archive HEAD` 的干净副本 `E:\code\bysj_audit_head` 上执行；H3/H4/H6 与 ROUND_32
> 前端测试在工作区执行（26 个 HEAD 跟踪的 `test_p2_*.py` 集合未变，工作区新增的
> p2_59 不在本轮范围）。**本报告所有数字若与 ROUND_33 工作区文件冲突，以 HEAD 为准。**

> **后记（2026-10-24）**：上述未提交的 ROUND_33（校准）改动已于当日入库
> （P2_59，见 `docs/P2_59_ROUND33_CALIBRATION_AUDIT.md`）。本报告的审计基线
> 仍为 HEAD `716677d` 及其 `git archive` 干净副本；后记之后 ROUND_33 的数字
> 以已提交产物与其审计文档为准，本报告不因后记回溯改数。

---

## 〇、总览表

> `Y` = 已提交产物 + 一条命令可复算；`P` = 部分可复算（需数据集/工件，或仅有日志）；
> `N` = 不可复算。完整逐轮五问见 §一。

| ROUND | commit | 审计文档 | 机器凭证 | 核心声明 | 可一条命令复算 |
|---|---|---|---|---|---|
| R1 | `f4a91b4` | `docs/CODE_REVIEW_2026-10-11.md`（P0 追记） | 无逐轮 test（总体套件） | 2026-10-11 源码审查 10 项 P0 整改 | P |
| R2 | `20498dc` | 同上（第二轮追记） | 无逐轮 test | fuse 非有限值/GDPR 稳定排序/上传响应头/禁静默造数 | P |
| R3 | `e4fe53c` | 同上（第三轮追记） | 无逐轮 test | 分组加人只回滚 savepoint/审计角色去硬编码/MLP 检查点加锁 | P |
| R4 | `a31ea1c` | 同上（第四轮追记） | 无逐轮 test | 推理并发有界/异常检测去 N+1 | P |
| R5 | `6e30efa` | 同上（第五轮追记） | 无逐轮 test | 前端 7 项（CSV 注入/白屏/401/悬垂拒绝） | P |
| R6 | `c61989a` | 同上（第六轮追记） | 无逐轮 test | 9 个统计卡改后端 SQL 聚合（F-03/#15） | P |
| R7 (P2-31) | `f5ce7e8` | `docs/P2_31_TENANT_QUERY_AUDIT.md` | `tests/test_p2_31_tenant_guard.py` | 租户隔离执行层 fail-closed | Y |
| R8 (P2-32) | `61b01f9`（+`a58f95c`） | `docs/P2_32_SSOT_DEDUP_AUDIT.md` | `tests/test_p2_32_ssot.py` | Blob 下载链路收敛 + 危机词表死副本清除 | Y |
| R9 | `7bc85e8`（+`63afdd2`/`721def3`） | `docs/P2_09_ROUND9_AUDIT.md` | `tests/test_p2_09_round9.py` | #32 余量/#33/#35/#39/#40 + E33 假闸门加固 | P（原始扫描器未入库） |
| R10 | `c29f0cb` | `docs/P2_10_ROUND10_AUDIT.md` | `tests/test_p2_10_round10.py` | #37 角色 helper/#32 余量/CSV 三处/#38 注释清单 | P（扫描器未入库） |
| R11 | `eba00f8`（+`f0cd16b`/`a0b68f1`） | `docs/P2_11_ROUND11_AUDIT.md` | `test_p2_11_round11.py` + `scan_p2_11_audit.py` + result json | #39 裁定/#33/#35 第一批/#36/类型 42→0 | Y |
| R12 | `52bd356`…`3e5969d` | `docs/P2_12_ROUND12_AUDIT.md` | `test_p2_12_round12.py` + `vitest_round12_baseline.*` | #34 收敛/#33 迁移/#36 分页/基建门禁 | Y |
| R13 | `52c5959`…`348674f`（+`f1c4b4e`） | `docs/P2_13_ROUND13_AUDIT.md` | 37 个 `mutate_p2_35_*_result.log` + `final_sweep_p2_35_round13_result.json` | #35 X 桶 W=103/X=116，总数 334 | Y |
| R14 | `f7be1b7`/`8713521` | `docs/ML_LEAKAGE_AUDIT.md` + `ML_LEAKAGE_REMEDIATION.md` | `tests/test_p2_38_leakage_audit_guard.py` | 41 文件/90 入口泄漏审计 + 护栏 | Y |
| R15 | `221db18` | `docs/planning/P2_R15_*.md`（3 份） | `test_p2_39_early_detection_guard.py` + 仿真/评估脚本 | 纵向早期检测 T3 阴性 + 可复现仿真 | P（G6 依赖语料，CI skip） |
| R16 | `9b763bf`/`d5b9da1` | `docs/planning/P2_R16_MODEL_VALIDATION_EVIDENCE.md` + TRIPOD json | `test_p2_40_model_validation_round16.py` | DCA/ECE/融合消融/公平性/漏报安全网/阈值 SSOT | Y |
| R17 | `5c60b05` | `docs/P2_17_ROUND17_AUDIT.md` | `test_p2_41_round17_auth_gate.py`/`_tenant_status.py` | 租户封禁止血开关 + 鉴权入口覆盖 | Y |
| R18 | `8e8ed1e`…`ae998eb` | `docs/P2_18_ROUND18_AUDIT.md` | `test_p2_42`…`test_p2_45` | M1/M2/M6/M7/M8/M9 六条 | Y |
| R19 | `6ce0ac6` | `docs/P2_47_ROUND19_M_BATCH2_AUDIT.md` | `test_p2_47_round19_m_batch2.py` | 审查报告 M 批 2 六条 | Y（含一处空断言，见红项 R6） |
| R20/R21 | — | — | — | **git 与 docs 中无任何记录（编号空洞）** | N/A |
| R22 | `2948428`/`3cabe24`/`713ead5` | `docs/P2_22_ROUND22_PORTFOLIO_AUDIT.md` | `test_p2_46_round22_portfolio_docs.py` + `check_portfolio_numbers.py` | 作品集一页概览 + 数字自检闸门 | Y |
| R23 | `02e1ab1`/`3acd5eb`/`29bf28a`/`2d2eb38`/`85a7850` | `docs/P2_23A_M13_AUDIT.md` + `P2_23B_FRONTEND_AUDIT.md` | `test_p2_48`/`p2_49`/`p2_50` | M13 并发唯一性 + 前端越权/秘密扫描/排序 | Y |
| R24 | `7cc22e7` | `docs/P2_51_ROUND24_PAGINATION_ORDER_AUDIT.md` | `test_p2_51_pagination_order_gate.py` + behavior | 分页排序确定性 AST 闸门 + 15 处次级键 | Y |
| R25 | `0dbe9cb`/`b2243f8` | `docs/P2_52_ROUND25_VERIFICATION_GAP_AUDIT.md` | `mutate_p2_52_round25*.log` + `p2_49`/`p2_51` | L13 脚本 4 入库/3 删除 + 判据扩展 14 修复 | Y |
| R26 | `6db38c1`/`aa83f46` | `docs/P2_53_ROUND26_EVAL_REPRODUCIBILITY_AUDIT.md` | `v1_29/01_reproducible_eval.py` + 已提交 csv/json（R28 闸门复算） | 逐样本分数 + bootstrap CI + D-R26-1 缺陷 | P（需 `datasets/`） |
| R27 | `931526c`/`a66ee72` | `docs/P2_54_ROUND27_TRANSFER_AUDIT.md` | `v1_29/02_transfer_eval.py` + 迁移预测 csv（R28 闸门复算） | 提交产物==单命令产物 + 18 格 0 真外迁 | P（需 `datasets/`） |
| R28 | `94e3f9d` | `docs/P2_55_ROUND28_THESIS_NUMBERS_AUDIT.md` | `test_p2_55_round28_thesis_numbers.py` + 数字闸门 | 台账 36 条 + 四份论文文档 + 闸门 | Y |
| R29 | `26d9681` | `docs/P2_56_ROUND29_SCALER_FIX_AUDIT.md` | `test_p2_56_round29_scaler_consistency.py` + 重训脚本 + 坏工件存档 | 修 D-R26-1，Recall 0.8727 / F1 0.8205 / AUC 0.9451 | P（CI 整模块 skip） |
| R30 | `310ffcb`/`e97591b` | `docs/P2_57_ROUND30_GROUPWISE_CI_AUDIT.md` | `test_p2_57_round30_groupwise_ci.py` + `groupwise_ci.json` | groupwise F1 0.5864 [0.5307, 0.6381] | Y（内容可复算；Windows 字节不一致，见红项 R4） |
| R31 | `979a0fa` | **无独立审计文档** | `test_p2_58_round31_eatd_scaffold.py` + `v1_31/` | EATD 外部锁定脚手架（预注册/只 transform） | Y（仅脚手架） |
| R32 | `716677d` | **无独立审计文档**（commit message 即记录） | `OnboardingTour.test.ts`/`guard.test.ts` + `mutate_round32_result.log` | 引导步骤双向绑定 + 根路径 fail-closed 重定向 | Y |

> 旁路提交：`f8e495e`（WESAD 落地 + 8 数据集获取工具）、`edaff4c`/`abb0f07`（百度取数）
> 不属于编号 ROUND，未纳入本表；其数据获取脚本在库、外部数据不在库。

---

## 一、逐轮五问（Q1 代码真在 / Q2 CI 机器凭证 / Q3 数字可复算 / Q4 被后续取代并标注 / Q5 自证嫌疑）

| ROUND | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|---|---|---|---|---|
| R1–R6 | ✓ | △ 无逐轮 test，只有总体套件 | ✗ 无逐轮产物/命令 | ✓ 被后续审查轮持续收敛 | 低 |
| R7 | ✓ `test_p2_31` 实跑 | ✓ 26 文件之一 | ✓ | N/A | 无 |
| R8 | ✓ `test_p2_32` 实跑 | ✓ | ✓ | N/A | 无 |
| R9 | ✓ | ✓ `test_p2_09` | △ 原始扫描器未入库 | N/A | 低（源码 token 断言；同轮已加固 E33 假闸门） |
| R10 | ✓ | ✓ `test_p2_10` | △ 扫描器未入库 | ✓ 被 R11/R12 继续收敛 | 低 |
| R11 | ✓ | ✓ `test_p2_11` + 扫描器/结果 json | ✓ | ✓ #32 由 R12 收尾关闭 | 低（棘轮常量/桶分类器自带） |
| R12 | ✓ | ✓ `test_p2_12` + 前端基线 | ✓ | ✓ | 低 |
| R13 | ✓ | ✓ 37 份变异日志 | ✓ | ✓ | 无 |
| R14 | ✓ | ✓ `test_p2_38` | ✓ | ✓ 基线 40/88→41/90 已在 `ML_LEAKAGE_AUDIT.md` 补记 | 无 |
| R15 | ✓ | △ `test_p2_39` G6 在 CI skip | △ 依赖语料/合成仿真 | N/A | 低 |
| R16 | ✓ | ✓ `test_p2_40` | ✓ | ✓ 论文侧数字后由 R29 更新，已标历史 | 无 |
| R17 | ✓ | ✓ `test_p2_41`×2 | ✓ | N/A | 无 |
| R18 | ✓ | ✓ `test_p2_42`–`45` | ✓ | N/A | 无 |
| R19 | ✓ | ✓ `test_p2_47` | ✓ | N/A | **中（一处子集断言恒空，见红项 R6）** |
| R22 | ✓ | ✓ `test_p2_46` + 独立路由计数 | ✓ | N/A | 无（有反弱化 + 负样本自证） |
| R23 | ✓ | ✓ `test_p2_48`/`49`/`50` | ✓ | ✓ 排序由 R24/R25 扩展 | 低（p2_50 前两例自建 SQL；p2_51 已补真闸门） |
| R24 | ✓ | ✓ `test_p2_51`×2 | ✓ | ✓ R25 扩展函数形态 | 无（闸门有自证三档） |
| R25 | ✓ | ✓ 变异日志 + p2_49/p2_51 | ✓ | N/A | 无 |
| R26 | ✓ | △ 无专属 test；脚本 + 产物 | △ 需 `datasets/`；csv/json 层可复算 | ✓ R29 取代 D-R26-1，P2_53 有取代声明 | 无 |
| R27 | ✓ | △ 无专属 test；脚本 + 产物 | △ 需 `datasets/`；csv/json 层可复算 | ✓ 修正 R26 门槛口径，P2_53 有更正块 | 无 |
| R28 | ✓ | ✓ `test_p2_55`（真子进程） | ✓ 39 条全部对拍 | △ R30 扩到 39 条，`REVIEWER_QA.md` 未同步（红项 R1） | 无（变异 8 臂） |
| R29 | ✓ | ✗ `p2_56` 整模块在 CI skip | △ 需数据集 + 未入库工件 + 坏工件存档 | N/A | **中（CI 证据声明不实，红项 R2）** |
| R30 | ✓ | ✓ `test_p2_57` | ✓ oof sha/计数/点估计一致 | N/A | 无（但审计 sha 声明错误，红项 R3；字节一致性红项 R4） |
| R31 | ✓ | ✓ `test_p2_58` | ✓（脚手架层） | N/A | 低（未显式断言 EATD 数据未跟踪） |
| R32 | ✓ | ✓ 23 passed | ✓ 变异日志 | N/A | 无 |

**Q2 的 CI 口径**：`.github/workflows/coverage.yml` 在 push/PR 上执行
`pytest tests/ -m "not contract"`，26 个 `test_p2_*.py` 均会被收集；但 `skipif`
会在干净 checkout 上生效（详见红项 R2 与 §六）。

---

## 二、硬性复核结果（H1–H6）

### H1 · 论文数字闸门 ✅

命令（干净 HEAD 副本）：

```bash
cd /e/code/bysj_audit_head/backend
E:/code/bysj/backend/.venv/Scripts/python.exe scripts/modeling/eval/verify_thesis_numbers.py
```

真实输出：

```text
论文数字校验 OK：台账 39 条 + 章节主表/迁移表/混淆矩阵/诊断表 + 黑名单 + 引用纪律，全部与已提交产物一致
H1_RC=0
```

`--show` 真值表（节选，完整 39 条全部打印）：

```text
C-01	0.8662420382165605
C-04	0.8205128205128205
C-05	0.9450980392156862
C-06	TP=48 / FP=14 / FN=7 / TN=88
C-12	0.5120428537721051
C-19	0.9861660079051383
C-22	0.5863937387116196
C-23	0.843672758736488
C-24	0.5375275938189845
C-25	0.6450331125827815
S-01	1029
S-04	682
S-05	8379
S-06	719 / 153 / 157
X-04	2→1 @0.55
X-06	0.55/0.3/0.15
SHOW_RC=0
```

**变异见证**（把 OOF 第 1 行 label 0→1）：

```text
sha_before=0dd48b4a9dbc93ef1e0c2e1c293e480f423c47ed880e2511e86ef03f0933dd22
sha_mutated=22663f9772d450cee758ef1a8f3e5865d0addfc67e9c73d606bc18f2a519b3c4
论文数字校验 FAIL：27 处不一致

  ✗ groupwise_ci.json 记录的 oof sha256 与当前 csv 不符：0dd48b4a… vs 22663f97…
  ✗ [groupwise_ci.json f1.point] 文档值 0.586394 vs 复算真值 0.5862172735479988（容差 1.001e-06）
  ✗ [台账 C-22（第 76 行）] 文档值 0.5864 vs 复算真值 0.5862172735479988（容差 5e-05）
  ✗ [章节 groupwise 表 F1 CI 下界] 文档值 0.5307 vs 复算真值 0.5305483584793713（容差 5e-05）
  …（共 27 条）
MUT_RC=1
sha_restored=0dd48b4a9dbc93ef1e0c2e1c293e480f423c47ed880e2511e86ef03f0933dd22
RESTORE_OK
论文数字校验 OK：台账 39 条 + 章节主表/迁移表/混淆矩阵/诊断表 + 黑名单 + 引用纪律，全部与已提交产物一致
GREEN_RC=0
```

结论：闸门**确实在复算**，不是自证；39 条台账与章节表格均与已提交产物一致。

### H2 · 可复算评估 ✅（有数据/工件时逐字节一致；干净 checkout 不可跑）

命令（干净 HEAD 副本，已补 `datasets/` 与生产工件）：

```bash
cd backend && .venv/Scripts/python.exe scripts/modeling/eval/v1_29/01_reproducible_eval.py --report-only
```

真实输出：

```text
[report-only] n=157 f1=0.8205 auc=0.9451 rec=0.8727 -> physio_v2_current_data_eval.json + PHYSIO_V2_EVAL_REPORT.md
H2_RC=0
```

与已提交产物的 sha256 对比（三者全等）：

| 产物 | 重跑 | HEAD | 结论 |
|---|---|---|---|
| `backend/models/artifacts/physiological_optimized/test_predictions.csv` | `1853a250…55cc94` | `1853a250…55cc94` | 逐字节一致 |
| `docs/model-evaluation/PHYSIO_V2_EVAL_REPORT.md` | `464431ff…d9e84` | `464431ff…d9e84` | 逐字节一致 |
| `docs/model-evaluation/physio_v2_current_data_eval.json` | `2d8d1906…0c4277` | `2d8d1906…0c4277` | 逐字节一致 |

**边界实测**：

1. 无原始数据集时命令直接失败（不是静默降级）：

```text
FileNotFoundError: Depresjon dataset not found: E:\code\bysj_audit_head\datasets\physiological\external\depresjon_processed\depresjon_physiological.csv
H2_NO_DATA_RC=1
```

2. 有 `datasets/` 但无模型工件（`model.json`/`scaler.json`/`cleaner_stats.json`/`feature_names.json`
   均未入库）时命令可跑，csv 与报告仍逐字节一致，**JSON 仅 `reproducibility.artifacts_sha256`
   不同**（`{}` vs 四个哈希）：

```diff
-  "artifacts_sha256": {},
+  "artifacts_sha256": {
+   "cleaner_stats.json": "234c69ff…",
+   "feature_names.json": "1d96dca6…",
+   "model.json": "d2b0b805…",
+   "scaler.json": "310ee08d…"
+  },
```

结论：ROUND_27 的「提交产物 == 单命令产物」在有完整本地状态时**成立**；干净 checkout
只能复算 csv/json 层，这不构成红项（ROUND_28 闸门 docstring 已如实记账），但审稿人
若只有数据集、没有工件，JSON 的 provenance 字段无法逐字节复现。

### H3 · 泄漏守卫 ✅

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/test_p2_38_leakage_audit_guard.py -q
```

真实输出：

```text
16 passed, 31 warnings in 150.46s (0:02:30)
H3_RC=0
```

独立跑扫描器：

```text
{"summary": {"total_findings": 90, "by_risk": {"group_aware_without_groups": 11,
 "random_split_no_groups": 63, "threshold_picking": 16}, "files_touched": 41}}
```

- 与守卫基线 `BASELINE_FILES=41` / `BASELINE_ENTRIES=90` 一致；
- `v1_30/groupwise_ci.py` 与 `v1_31/*.py` **均不在** findings 文件集合中
  （独立 grep 也确认只有 `ln.split(",")` 的字符串切分，无 `fit`/`train_test_split`）。

### H4 · 26 个 P2 机器凭证逐条跑 ✅

```bash
cd backend && .venv/Scripts/python.exe -m pytest $(ls tests/test_p2_*.py | tr '\n' ' ') -q -p no:cacheprovider
```

真实输出（尾部）：

```text
TOTAL                                            24685  13870   6042    565    39%
544 passed, 44 warnings in 727.78s (0:12:07)
H4_RC=0
```

范围：26 个 HEAD 跟踪的 `test_p2_*.py`（p2_09 至 p2_58，含 p2_31/32）。
工作区新建、尚未提交的 `test_p2_59_round33_calibration.py` 不在本轮范围。
本机有数据与工件，故 p2_56 五例、p2_38 真实语料例均实际执行（CI 上会 skip，见 R2）。

### H5 · ROUND_30 groupwise CI 自洽 ✅（内容一致；Windows 字节不一致）

```bash
cd backend && .venv/Scripts/python.exe scripts/modeling/eval/v1_30/groupwise_ci.py
```

真实输出：

```text
[groupwise_ci] n=8379 groups=1277 F1=0.5864 [0.5306988743693593, 0.6381469293233998] AUC=0.8437 [0.8169730130607495, 0.8696216566969442]
H5_RC=0
```

哈希对比：

```text
HEAD  groupwise_ci.json  c40fa308e47775089b5f87ba5bbd2b373e2c0efbf9be2db56e7f1f9bb4f2759b（LF）
重跑  groupwise_ci.json  df9266241be584df2b5f06691c705ea7ea11a73c00e447237e7844d2f3cb9c79（CRLF，38 个 CRLF）
LF 归一后两者均为 c40fa308e47775089b5f87ba5bbd2b373e2c0efbf9be2db56e7f1f9bb4f2759b
```

- `oof_csv_sha256` = `0dd48b4a9dbc93ef1e0c2e1c293e480f423c47ed880e2511e86ef03f0933dd22`，
  与 CSV 的 LF 归一 sha **相等**；
- 四指标点估计与 CI 与 H1 台账真值一致；`method` 明写「resample 1277 groups」；
- **但在 Windows 上不是逐字节一致**（提交件 LF vs 重跑 CRLF），见红项 R4。

### H6 · ROUND_31 外部测试脚手架未越界 ✅

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/test_p2_58_round31_eatd_scaffold.py -q
```

真实输出：

```text
4 passed, 4 warnings in 46.10s
H6_RC=0
```

独立证据：

- `git ls-files | grep -i eatd` 仅 5 项：`EATD_DOWNLOAD_GUIDE.md`、`EATD_PREREGISTRATION.md`、
  `eval_eatd_locked.py`、`validate_eatd.py`、`test_p2_58_round31_eatd_scaffold.py`——**无数据文件**；
- 本地 `data/external/eatd/`、`backend/data/external/eatd/` 均不存在；
- `grep -rE "\.fit\(|\.fit_transform\(|partial_fit|train_test_split"` 于 `v1_31/` 返回 **NONE**；
- 测试以 AST 禁 `fit/fit_transform/partial_fit/train_test_split`（`test_p2_58:22-50`）。

### ROUND_32 前端复核 ✅

```bash
cd frontend && npx vitest run src/components/common/OnboardingTour.test.ts src/router/guard.test.ts
```

真实输出：

```text
Test Files  2 passed (2)
Tests       23 passed (23)
Duration    45.70s
R32_RC=0
```

`mutate_round32_result.log`（已入库）记录 M1/M2/M3 三臂 RED、还原 sha 一致、
恢复后 4 passed / 19 passed；与本次复跑一致。

---

## 三、文档一致性三角核对

### 3.1 台账与四份文档

- 台账 HEAD 共 **39 条**：C-01~C-25（25）+ S-01~S-08（8）+ X-01~X-06（6）。
- 闸门 `check_ledger`/`check_chapter`/`check_blacklist`/`check_citation_discipline`
  全部 rc=0（H1）。
- 黑名单 B-01~B-05 在台账 §二完整；B-01 的不可复现三重证据（719/153/157 vs 719/171/139、
  `scaler.json` 域外、脚本未入库）与 `scaler.json.broken_round29` 存档一致。
- 易漂移四处逐一核对：

| 漂移点 | 现行文档 | 判定 |
|---|---|---|
| 生理域内 F1 0.8205 vs 历史 0.8542 | `RESULTS_CHAPTER`/`LIMITATIONS` 用 0.8205 [C-04]；0.8542 只出现在台账 B-01 黑名单行（带拒绝标记） | ✅ 未混用 |
| 迁移 AUC 0.5120 | `RESULTS_CHAPTER:103/106/147/196`、`LIMITATIONS §2.1` 均写「与随机不可区分/CI 覆盖 0.5」 | ✅ |
| 文本 OOD 0.9862 | `RESULTS_CHAPTER:104/109-111/113/196` 均写「同源泄漏」「不得当泛化」 | ✅ |
| groupwise F1 0.5864 | C-22 备注 + `RESULTS_CHAPTER:115-118` + `LIMITATIONS §2.2` 均写「同人群换被试，非跨平台/跨人群」 | ✅ |

### 3.2 三角核对红项

1. **`REVIEWER_QA.md:79` 写「台账全部 35 条登记」，HEAD 实为 39 条。**
   该错从 R28 就存在（R28 建台账 36 条、QA 写 35）；R30 加 C-23~C-25 后仍写 35。
   `RESULTS_CHAPTER.md:182` 已正确写 39，`test_p2_55` docstring 仍写 36（见 §五 R7）。
2. **兼容性备注缺产物路径**：`CLAIMS_LEDGER.md:89-93` 的 C-22 备注引用
   `0.9964 / 0.9994`，但未给入库产物路径/复算命令。实际产物存在：
   `backend/scripts/modeling/v1_27/bilingual_groupwise_retrain_results.json`
   （`textwise_ooF.f1=0.9964`、`roc_auc=0.9994`，n=8379）。
   同一来源文档 `docs/ML_LEAKAGE_AUDIT.md:172` 另有 `0.8860 / 0.9994`（1244 组、
   阈值 0.3 的另一协议），未与 0.9964 的协议区分——易被读者误读为矛盾。

### 3.3 黑名单与引用纪律

- `check_blacklist` 通过：0.8542/0.9653/0.9530/0.8527/139 等 token 在四份文档中
  只以拒绝性语境出现。
- `check_citation_discipline` 通过：QA/LIMITATIONS 中 ≥3 位小数的数字均同行带编号
  或拒绝标记。
- 但 `FINE_NUM` 只查 QA/LIMITATIONS，不查 `RESULTS_CHAPTER`；章节中的派生数
  （−0.41 / −0.156）依赖 C-22 备注解释，未单列编号。属可接受的展示口径，记账为低风险。

---

## 四、跨轮因果链审查

| 后轮 → 前轮 | 修正内容 | 前轮文档是否正确标注 |
|---|---|---|
| R27 → R26 | 「report-only 与 json 一致」不成立；根因是行序（非精度）。改为 `.17g` csv + 按落盘序算 CI + report-only 写 JSON | ✅ `P2_53` 顶部有 ROUND_27 更正块，含旧值 `[0.638282, 0.843137]` 的复现说明 |
| R29 → R26 | D-R26-1（scaler 与数据版本不配套）修复；0.6000/0.7500/0.9884/TP=33 降为历史口径 | ✅ `P2_53` 顶部有 ROUND_29 取代声明；台账 C-01~C-06 改为修复后读数；坏工件存档 `*.broken_round29` |
| R29 → R28 | C-07~C-09 由「缺陷定位诊断列」改为「co-consistency 证明列」 | ✅ 台账 C-22 前备注明确记录语义变更与历史值 0.9369/0.9455/0.9841 |
| R30 → R28 | 台账 36→39（C-22 升级带 CI，新增 C-23~C-25）；章节新增 4bis | △ 台账/章节正确；`REVIEWER_QA.md` 未同步（红项 R1） |
| R30 fix → R30 | OOF sha 改行尾归一（72b451e6→0dd48b4a）；审计文档同步 oof sha | △ oof sha 已同步；但 `groupwise_ci.json` 的「逐字节 sha」仍写 `B9E38E01…`（红项 R3） |
| R16 → R14 | 泄漏基线 40/88→41/90（新增 fusion_ablation 合规入口） | ✅ `ML_LEAKAGE_AUDIT.md:122-138` 有 ROUND_16/ROUND_26 两段补记 |
| R25 → R23b | L13 脚本「修了但 CI 无人看管」缺口 → 4 入库/3 删除 + 记账闸门 | ✅ `P2_52` §〇 明确写出前轮缺口与兑现方式 |
| R29 → R27 | 「提交产物 == 单命令产物」在换 artifact 后复验 | ✅ `P2_56` §五记录 `--report-only` 与全量运行逐字节一致；H2 本次实测三件产物 sha 全等 |

**结论**：主链 R26→27→28→29→30→31→32 的推翻/替代关系基本都已在前轮文档留痕；
唯二的断点是 R28/R30 没同步 QA 计数、R30 审计文档残留错误 sha。

---

## 五、红项清单（按严重度）

### 致命（数字与产物不符）

**0 项。** H1 闸门 39 条全部与产物一致；四份论文文档没有把黑名单数字当结果；
四个易漂移点的定性标注全部正确。

### 高（脚本/闸门不可复算或不在 CI 执行）

**R1. R9/R10 审计引用的扫描器从未入库，原始清单不可复算。**
- 证据：`docs/P2_09_ROUND9_AUDIT.md:4` 引用 `backend/scripts/scan_p2_09_roles.py` /
  `scan_p2_09_rest.py`；`docs/P2_10_ROUND10_AUDIT.md:3` 引用
  `backend/scripts/scan_p2_10_roles_be.py` / `scan_p2_10_fe38.py`。
  `git ls-files` 无这些文件；`git log --all -- '*scan_p2_09*' '*scan_p2_10*'` 为空；
  工作区也不存在。对比：R11 的 `scan_p2_11_audit.py` + result json 已入库。
- 影响：R9/R10 的「#32/#33/#35/#37/#38 清单」只能看审计文档转述，不能一条命令重扫。
- 修复方向：补入库扫描器 + 结果 json（若原始脚本已丢失，则在两份审计文档明确标注
  「扫描器未入库，本清单为历史口径，不可复算」）。

**R2. R29 的 P0 防复发闸门在 CI 中整模块 skip，审计却声称「CI 侧只有工件层证据」。**
- 证据：`backend/tests/test_p2_56_round29_scaler_consistency.py:105-108` 的
  `pytestmark = pytest.mark.skipif(not (MODEL_JSON.exists() and SCALER_JSON.exists()
  and FEATURE_NAMES_JSON.exists()), ...)`；而这四个工件**均未入库**
  （`git ls-files backend/models/artifacts/physiological_optimized/` 只有 README/manifest/
  test_predictions）。`.github/workflows/coverage.yml` 也没有恢复模型工件的步骤。
  `docs/P2_56_ROUND29_SCALER_FIX_AUDIT.md:141-142` 写「工件在、数据集不在时第二/结构层
  照常跑……CI 侧只有工件层证据」——干净 checkout 里工件不在，**CI 一层都不跑**。
- 影响：P0 修复的对拍闸门只在数据机器有牙；CI 无任何相关断言（论文数字层仍由 p2_55
  闸门从已提交 csv 复算，故不影响 H1 结论）。
- 修复方向（二选一）：
  (a) 把四个工件纳入版本库或由 CI 从受控 artifact 恢复，让第二/结构层在 CI 跑；
  (b) 如实改文档为「CI 无证据；p2_56 仅数据机器执行」，并把 p2_56 标为 data-machine gate。

### 中（文档缺标注/声明与事实不符）

**R3. ROUND_30 审计文档的确定性 sha `B9E38E01…` 无任何对应产物。**
- 证据：`docs/P2_57_ROUND30_GROUPWISE_CI_AUDIT.md:27`；`git grep B9E38E01` 全库仅此一处。
  实际提交版 sha 为 `c40fa308…`（`310ffcb` 时为 `3f62223d…`，`e97591b` 重生成后为
  `c40fa308…`）；本次 Windows 重跑为 `df926624…`（CRLF），LF 归一后 `c40fa308…`。
- 修复方向：将 `B9E38E01…` 改为 `c40fa308…`，并写明「同内容以 LF 归一后比对；
  Windows 工作区新生成文件为 CRLF」。

**R4. H5「逐字节相同」在 Windows 上不成立（CRLF vs LF）。**
- 证据：`backend/scripts/modeling/eval/v1_30/groupwise_ci.py:118`
  `OUT_JSON.write_text(json.dumps(...))` 未指定 `newline`，Windows 写 CRLF（38 处）；
  提交件为 LF。内容 LF 归一后 sha 完全相同。
- 修复方向：`write_text(..., newline="\n")`（Python ≥3.10），或把声明改为
  「LF 归一后逐字节一致」。

**R5. `REVIEWER_QA.md:79` 台账条数 35 vs 39。**
- 证据见 §3.2；R28 创建时就是 35 vs 36，R30 扩到 39 未同步。
- 修复方向：改为 39；建议在闸门 `REQUIRED_QA_MARKERS` 或 `check_chapter` 增加
  「QA 计数 == 台账实际条数」的断言，防再漂。

**R6. `test_p2_47` 的「匿名化触及模型 ⊆ 导出清单」断言恒真（自证）。**
- 证据：`backend/tests/test_p2_47_round19_m_batch2.py:702-706`

```python
covered_models = set(MODEL_TO_SECTION)
missing = sorted(
    name
    for name in touched & covered_models
    if name not in MODEL_TO_SECTION
)
```

  `touched & covered_models` 已限定在 `MODEL_TO_SECTION` 内，后面的 `if` 永远为假，
  `missing` 恒空。反向检查（登记表模型必须在匿名化源码出现）有效，但「新增模型被
  匿名化触及却漏登记」这个方向无牙。
- 修复方向：从 `app.models` 的模型类集合（或 `session.query(...)`/`delete(...)` 的
  AST 形态）求候选，再做 `candidates - set(MODEL_TO_SECTION)`；不要用全量 `ast.Name`。

**R7. `0.9964 / 0.9994` 在论文台账中无独立编号/产物路径，且同源文档存在另一协议读数。**
- 证据：`docs/thesis/CLAIMS_LEDGER.md:89-93`（只有备注，无路径/命令）；
  `docs/ML_LEAKAGE_AUDIT.md:14`（0.9964）与 `:172`（0.8860/0.9994，1244 组、阈值 0.3）。
- 修复方向：在 C-22 备注补
  `backend/scripts/modeling/v1_27/bilingual_groupwise_retrain_results.json`（`textwise_ooF`）
  与复算命令；并注明 `0.8860` 是另一协议（组定义/阈值不同），避免读者误判矛盾。

### 低（注释/记账）

**R8. `test_p2_55` docstring 仍写「台账 36 条」。**
- 证据：`backend/tests/test_p2_55_round28_thesis_numbers.py:8`；HEAD 实为 39 条。
- 修复方向：改为 39（或写「R28 时 36 条，R30 起 39 条」）。

**R9. `test_p2_50` 前两例断言的是测试自己拼的 SQL，不是生产实现。**
- 证据：`backend/tests/test_p2_50_round23b_warning_order_stability.py:40-69`；
  第三例（`:71`）读生产源码，且 R24 的 `p2_51` AST 闸门已覆盖全仓，风险已被兜底。
- 修复方向：前两例改为导入 `services` 的真实 `list_warnings` 并编译其 statement，
  或删除并以 p2_51 为准。

**R10. `test_p2_58` 未显式断言「EATD 数据不在库」。**
- 证据：`backend/tests/test_p2_58_round31_eatd_scaffold.py:22-57` 只断言脚手架文件
  存在/可解析/无 fit-split/已入库；H6 提示词要求的「数据未跟踪」由人工 `git ls-files` 补证。
- 修复方向：增加 `git ls-files | grep -i eatd` 仅返回脚手架白名单的负向断言。

**R11. R31/R32 无独立审计文档。**
- 证据：`docs/` 无 `P2_58_ROUND31_*` / `ROUND_32_*`；R31 只有测试 + `v1_31/` 文档，
  R32 只有 commit message + 变异日志。
- 修复方向：补两份短审计（或明确「commit message + 变异日志即该轮审计凭证」）。

**R12. R20/R21 编号空洞。**
- 证据：`git log --all` 与 `git grep -i "round[_ ]*2[01]"` 均无记录；R19 后直接 R22。
- 修复方向：在版本记录中注明「R20/R21 未发生（编号跳过）」，避免后人误以为漏档。

---

## 六、自证嫌疑清单

| 测试/闸门 | 判定 | 说明 |
|---|---|---|
| `test_p2_47:702-706` | **中·空断言** | 子集检查恒空（红项 R6），反向检查有效 |
| `test_p2_50:40-69` | 低·弱见证 | 前两例自建 statement；第三例读源码，p2_51 AST 闸门兜底 |
| `test_p2_09` / `test_p2_10` / `test_p2_11` | 低·源码 token | 多处 `assert "字符串" in 源码`，注释/同名 token 可满足；R9 已自纠 E33「假闸门」并加固 |
| `test_p2_58` | 低·缺负向断言 | 只证脚本不 fit/split，未证数据未跟踪（红项 R10） |
| `test_p2_56` | 中·CI 无执行 | 非自证，但 CI 整模块 skip（红项 R2） |
| `test_p2_38` / `test_p2_39` | 已披露·数据 skip | mmpsy/语料不在库时单例 skip，注释与审计如实记账 |
| `test_p2_46` | **无嫌疑** | 读 README/摘要与真实产物，含「改坏一个数字必须红」的负样本自证 |
| `test_p2_51` | **无嫌疑** | AST 读生产源码 + 三档自检 + 白名单防腐 + 防空转 |
| `test_p2_55` | **无嫌疑** | 真子进程跑真闸门 + AST 只读断言 + 8 臂变异 |
| `test_p2_57` | **无嫌疑** | 产物存在/method 不退化/oof sha 自洽/计数对 csv/点估计对 eval json |
| R32 前端两测试 | **无嫌疑** | 真实组件挂载 + 三臂变异（:current / 删根分支 / 去 roleVerified） |

---

## 七、不可复算清单（如实记账）

1. **R1–R6**：无逐轮产物/命令，只有 `docs/CODE_REVIEW_2026-10-11.md` 追记与总体测试套件。
2. **R9/R10**：`scan_p2_09_*` / `scan_p2_10_*` 扫描器未入库，清单不可重扫。
3. **PHQ-9 数据集 682 行（S-04）**：数据不在库、无 json 工件，只做跨文档对齐
   （`LIMITATIONS §1.2` 已如实记账）。
4. **融合权重敏感性 csv**：生成脚本未入库；闸门只验 csv 内部一致性（公式/阈值/生产权重行），
   台账 §1.4 已注明。
5. **R26/R27/R29 全量重跑**：需 `datasets/`；R29 还需未入库的模型工件与
   `*.broken_round29` 存档。干净 checkout 只能复算 csv/json 层（H2/H1 已实测）。
6. **R15 G6 基准不变量**：依赖 `chinese_depression_corpus_v1.csv`，CI 上 skip
   （`test_p2_39:277`）。
7. **R29 的「同 seed 两跑逐字节一致」**：需数据机器，本轮未重跑，仅引用审计记录与
   H1/H2 的产物级一致性。
8. **EATD 外部数据**：不在库（设计如此），只能验证脚手架未越界（H6）。

---

## 八、结论与最小修复清单

### 结论一句话

**30 个有记录的 ROUND（R1–R19、R22–R32；R20/R21 无记录）中，14 轮完全可复核、
16 轮部分可复核、5 轮存在文档-产物不一致（R9、R10、R28、R29、R30）；致命级 0 项，
论文主结果（39 条台账 + 四份文档）与已提交产物一致。**

### 最小修复清单（按提示词 §六，等确认后再动）

**A. 只改文档（在本次授权范围内，建议优先）**

1. `docs/thesis/REVIEWER_QA.md:79`：35 → 39。
2. `docs/P2_57_ROUND30_GROUPWISE_CI_AUDIT.md:27`：`B9E38E01…` → `c40fa308…`，
   并注明「LF 归一后逐字节一致；Windows 工作区生成 CRLF」。
3. `backend/tests/test_p2_55_round28_thesis_numbers.py:8`：36 → 39。
4. `docs/P2_56_ROUND29_SCALER_FIX_AUDIT.md:141-142`：
   「CI 侧只有工件层证据」→「CI 无工件层证据；p2_56 整模块因工件未入库而 skip，
   证据仅来自数据机器」。
5. `docs/thesis/CLAIMS_LEDGER.md:89-93`：给 0.9964/0.9994 补入库产物路径与复算命令，
   并注明 `ML_LEAKAGE_AUDIT.md:172` 的 0.8860 属另一协议。
6. `docs/P2_09_ROUND9_AUDIT.md:4` / `docs/P2_10_ROUND10_AUDIT.md:3`：标注扫描器未入库
   （或补入库脚本 + 结果）。

**B. 改测试/脚本（超出「只读复核」边界，建议另立轮次）**

7. `groupwise_ci.py:118`：`write_text(..., newline="\n")`，消除平台字节差。
8. `test_p2_47:702-706`：修正恒空子集断言（用模型类候选集，不用全量 AST Name）。
9. `test_p2_50:40-69`：改为断言生产 service 的真实 statement（或删除，以 p2_51 为准）。
10. `test_p2_56`：给 CI 提供工件恢复方案，或明确降级为 data-machine gate。
11. `test_p2_58`：增加「EATD 数据未跟踪」负向断言。

**C. 只记账**

12. R20/R21 编号空洞、R31/R32 无独立审计文档：在版本记录/README 注明。

> 本报告只读复核，未修改任何业务代码、测试、论文文档或 ROUND_33 在建文件。
> A 组 6 条为最小文档纠错；B 组涉及测试/脚本行为，需单独授权。

---

## 九、编号与凭证说明（ROUND_34 补记）

- **R20/R21 为编号空洞**：`git log --all` 与 `git grep -i "round[_ ]*2[01]"` 均无记录，
  R19 后直接 R22；不是漏档。
- **R31/R32 无独立审计文档**：R31 以 commit `979a0fa` + `test_p2_58_round31_eatd_scaffold.py`
  + `backend/scripts/modeling/eval/v1_31/` 为凭证；R32 以 commit `716677d` + 前端 23 passed
  + `mutate_round32_result.log` 为凭证。
- **时点说明**：本报告结论中的「39 条台账」是 HEAD `716677d` 的时点值；ROUND_33
  （`09564c5`）新增 C-26~C-33 后为 47 条，校准轮以其审计文档为准。
- **修正状态**：本报告 §八 的 A 类 6 条已由 ROUND_34 处理（A1/A3 的计数按 ROUND_33
  后台账实数写为 47）；B 类 5 条已由 ROUND_35（`2546cb2`）处理完毕：B1 写盘固定 LF、
  B2 恒空断言改为 AST 导入对照（并豁免无 PII 的 `RefreshTokenSession`）、B3 改断言
  生产实现、B4 显式 data-machine-only gate、B5 EATD 未入库负向断言。CI 7/7 success。

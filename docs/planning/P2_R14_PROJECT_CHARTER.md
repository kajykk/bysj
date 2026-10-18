# P2 新阶段（答辩后）立项文档：从「工程完整」到「可解释 + 前沿对齐」

> 日期：2026-10-19｜上一里程碑：第十三轮 #35 闭环（HEAD `f1c4b4e`，CI check-runs total_count=10 全 success）

## 〇、开工前置（已实测，非转引）

| # | 核验项 | 实测结果 |
|---|---|---|
| 1 | HEAD = origin/main | ✅ 同为 `f1c4b4e1771faebad37573c1e9be557ac9eede44`，分支 `main` |
| 2 | `git diff` = 0 | ✅ 内容 diff **0 字节**。`git status` 报 61 个 `M` **全是假报**（CRLF 转换 + stat 缓存陈旧）；另有 2 个未跟踪运行时产物（`backend/pool93.json`、`backend/tests/tools/verify_p2_35_batch34_result.json`），按入库惯例不入库 |
| 3 | #35 棘轮 | ✅ 全称注释数 = 100（`test_inventory_ratchet_be` passed）；桶计数 **W=103 / X=116 / P=15 / S=34 / R=3，总数 334 不变**（`test_batch6_bucket_counts_pinned` passed） |
| 4 | 数据可用性 | 见 §一（**结论推翻了提示词的降级前提，但结论方向一致**） |
| 5 | P2-1 / P2-2 口径 | ✅ 已读。P2-1：groupwise F1 **0.5864** 为泛化口径；样本内 `full_model_eval_on_zh` F1 0.9972 **不可当泛化引用**。P2-2：中性字段 **kappa 0.00 / 一致率 0.50** |

> 注：核验 #3 时踩到一个坑并已修正——#35 的「桶计数棘轮」在
> `test_p2_11_round11.py::test_batch6_bucket_counts_pinned`，
> 全称注释棘轮在 `test_p2_10_round10.py::TestP238Comments`（**不是**
> `TestP2_10_DegradationInventory`；用错类名时 pytest 静默 0 收集，
> 这正是「0 收集 = 红色信号」纪律要抓的情况）。

## 一、数据可用性实测（决定方向 A 的生死）

### 1.1 逐条目 PHQ-9 标注到底有没有？

| 数据 | 行数 | 文本列 | PHQ-9 逐条目 |
|---|---|---|---|
| `data/external/chinese_depression_corpus_v1.csv` | 8379 | ✅ `text` / `audio_transcript` | ❌ 只有 `phq9_score/level/binary`（总分） |
| `data/external/chinese_depression_corpus_v2(_clean)` | 同结构 | ✅ | ❌ 仅总分 |
| `data/external/aligned_features.csv` | 28552 | ❌ 无 | ❌ 仅 `phq9_total/severity` |
| `data/external/mmpsy_scores.csv` | 1275 | ❌ 无 | ❌ 仅总分 |
| **`datasets/PHQ-9_Dataset_5th Edition.csv`** | **682** | ❌ **无文本列** | ✅ **9 项齐全**（0–3 分制） |

⇒ **关键结论（比提示词预想更精确）**：
不是简单的「有/没有逐条目标注」，而是——
**「文本」与「逐条目 PHQ-9 标签」落在两份互不相交的数据上**：

- 有文本的那份（中文语料 8379 行）**只有总分**，没有 9 条目；
- 有 9 条目的那份（PHQ-9 Dataset 682 行）**没有文本**。

**后果**：无法构造「证据片段 → 症状判断」的监督样本对。
即使模型从访谈文本里摘出「我整晚睡不着」并判「睡眠条目 = 2 分」，
也没有对应的条目级标签可供比对 ⇒ **方向 A 的门槛①（≥ 现役分类器）无法在系统化指标上验证**，
只能退回人工抽查——那已不是「评估层」，而是「演示」。

### 1.2 因此本轮的选择

按提示词 §四：「先只做方向 B 也完全可接受——它是 A/C 的前置纪律，成本最低。」
本轮**执行方向 B**，并把上面这条数据裁定写死，避免后续重复踩坑。

## 二、方向 B 执行结果

完整清单与裁定见 **`docs/ML_LEAKAGE_AUDIT.md`**。摘要：

- 全仓本仓自研 ML 划分入口：**42 文件 / 92 处**（AST 扫描，排除 `tests/` 与第三方副本）
- 建立三类问题定义：L1 随机划分不守恒 / L2 逐层挑优 / L3 阈值在评估集上选 / **L4 目标泄漏**
- 实证「泄漏前后指标差」（核心产出）：

| 数据 | ΔF1 | ΔAUC |
|---|---|---|
| `chinese_depression_corpus_v1`（1275 组增强变体） | **+0.3111** | **+0.1573** |
| `mmpsy_structured_features`（218 组特征碰撞） | +0.0014 | +0.0000 |

### 2.1 本轮最有价值的发现：L4 目标泄漏

`backend/scripts/modeling/v1_24/01_build_mmpsy_features.py`：

```python
def derive_stress(phq9: float) -> float:
    return round(phq9 / 27.0 * 5.0, 4)
```

`stress_level` 是 PHQ-9 总分的**确定性线性变换**，而标签 `phq9_binary = (phq9_score >= 10)`
（实测：`=1` 最小 10 分，`=0` 最大 9 分）。实测印证：`corr = 1.0`、**单特征 AUC = 1.0000**。

⇒ 凡以 `stress_level` 为输入的 mmpsy 评估读数（含
`v1_24/02_validate_mmpsy.py:87` 的 `cross_val_score(cv=5)` 3-feature 基线）
都是**同义反复**。且 **L4 换任何 CV 都修不好**，只能改特征集。

### 2.2 对方向 B 前提的修正（重要）

mmpsy 那份数据重复率高达 55.9%，但实测 Δ≈0。原因不是没泄漏，而是**天花板效应**
（该任务 12 个特征本就 AUC 0.9996 近乎完美可分）。

⇒ **「数据有重复」≠「指标虚高」。** 一刀切判「随机划分 = 泄漏」是错的，
必须按「数据是否有兄弟结构」+「实测 Δ」两层判定。这条已写入审计文档。

## 三、门槛对照

| 提示词要求（方向 B） | 达成 | 证据 |
|---|---|---|
| 审计清单 100% 覆盖既有 ML 评估脚本 | ✅ | 42 文件 / 92 入口全量 AST 扫描 + 逐条人工核对 |
| 每条给出「泄漏前后指标差」实证 | ⚠️ 部分 | 两条主线已实测落盘（见 §二表）；**4 处阈值挑优未逐条核实**——见 §五记账 |

⚠️ 为何是「部分」：扫描器只能识别「存在 `best_threshold`/`best_f1` 赋值」这一**形态信号**，
无法判断阈值是在训练折内选还是在评估集上选。这需要人工读码，本轮未完成，
**不做任何乐观推断**。

## 四、产出清单

| 文件 | 说明 |
|---|---|
| `docs/ML_LEAKAGE_AUDIT.md` | 审计清单（42 文件 / 92 入口，含裁定与实证） |
| `docs/planning/P2_R14_PROJECT_CHARTER.md` | 本立项文档 |
| `backend/tests/tools/leakage_audit_scan.py` | AST 扫描器（粗排），输出候选 JSON |
| `backend/tests/tools/leakage_delta_probe.py` | 双口径对照 + 目标泄漏检测 + `--self-test` |
| `backend/tests/test_p2_38_leakage_audit_guard.py` | 8 条闸门 |
| `backend/tests/tools/mutate_p2_38_round14.py` | 4 个真实变异 |
| `backend/tests/tools/mutate_p2_38_round14_result.log` | 变异日志 |

## 五、未验证 / 记账（不得省略）

1. **4 处阈值/权重挑优未核实评估集是否被污染**：
   `scripts/m5_calibration_thresholds.py`（`best_threshold`×2）、`scripts/eval_model.py`
   （×1）、`backend/scripts/modeling/v1_26/01_threshold_sweep.py`、
   `scripts/optimize_fusion_weights.py`（`best_f1`×2）。**下轮必须人工读码补裁定。**
2. **`aligned_features.csv` 的 56 个完全重复行**对 v1_23 划分的影响未量化
   （占 0.2%，预估可忽略，但**未实测**）。
3. **本轮只检测不整改**：未改动任何 ML 脚本口径，未改动现役预测主路径。
   所有发现为新增记账，**不修正任何历史读数**。
4. **方向 A 未执行**，其可行性已被 §一数据裁定为「当前语料下不可做监督评估」，
   若要推进须先解决「文本 × 条目标签不相交」（见 §六出路）。
5. **方向 C 未执行**。
6. 工具缺陷已修但值得留档：扫描器路径常量曾漏扫 4 倍入口（见 §〇注）。

## 六、方向 A 的合规出路（供下一轮决策，本轮不执行）

当前障碍：有文本的数据无条目标签，有条目标签的数据无文本。可行出路：

1. **人工标注条目级标签**：对中文语料抽样（如 200–300 条）打 9 条目标签。
   ⚠️ 但提示词新增纪律①（引 `2610.14961`）：**小 N 上不默认微调**，
   先跑 frozen 编码器基线再谈微调；且域适配会抬高 κ 却压低总分。
2. **弱监督 + 人工校验**：用规则/LLM 从文本推断条目分数，再人工抽样校验。
   ⚠️ P2-2 已证明 LLM 在该任务上无判别力，且合规限制不传原文 ⇒ 此路当前不通。
3. **降级目标（推荐）**：方向 A 改为「总分 + 可检索证据」，门槛改为
   「证据-结论一致性人工抽查达标 + 总分不倒退」。
   这放弃「逐条目标签对齐」，但保住「可审计」这一核心诉求。

**未决**：以上三条未做成本/合规核算，**本轮不做推荐之外的任何承诺**。

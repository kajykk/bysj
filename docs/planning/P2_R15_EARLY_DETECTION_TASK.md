# P2 方向 C（ROUND_15）：eRisk 式纵向早期检测 —— 任务与指标定义

> 轮次：ROUND_15（2026-10-19）。上游：方向 B（检测，`be28cae`）、方向 B.5（补救，`8713521`）。
> 本轮目标：把交付从「时点筛查」升级为「纵向早期预警」——对齐 2026 eRisk Task 2
> 学习式停止策略（`2609.08161`）。**改的是评估范式，不是现役预测主路径。**

---

## 〇、数据可行性 gate（先实测，结论：无真实纵向数据）

### 0.1 已复现：外部语料非纵向

| 量 | 实测值 |
|---|---|
| `data/external/chinese_depression_corpus_v1.csv` 行数 | 8379 |
| `user_id` 唯一数 | **8379（每行即一个独立"用户"）** |
| 时间戳类列 | **无**（列全集：user_id / phq9_score / phq9_level / phq9_binary / gad7_* / audio_count / audio_transcript / text / augmentation / source_idx） |

⇒ **非纵向**，不能直接当用户时序。注意它有 `source_idx`（1244 组增强变体），
但那是同一文本的增强副本，不是同一用户的多时点观测。

### 0.2 生产 / seed 数据的纵向性实测（本 gate 的决定性部分）

Schema 层面**完全支持**纵向（先读代码确认，再查数据）：

| 模型 | 时间列 | 索引 | 文件 |
|---|---|---|---|
| `TextEntry` | `created_at` | `index=True` | `app/models/assessment.py:37-48` |
| `StructuredAssessment` | `created_at` | `index=True` | 同文件 `:25-34` |
| `PhysiologicalRecord` | `recorded_at` | `index=True` | 同文件 `:51-76` |
| `RiskAssessment` | `created_at` + `is_latest` | `ix_risk_assessments_user_created` | `app/models/risk.py:23-74` |

**实际数据（本机 sqlite 实测，非转引）**：

| 库 / 表 | 行数 | distinct user | 多时点用户 | top |
|---|---|---|---|---|
| `depression_system.db` / `text_entries` | 5 | 1 | **1** | user 9 = 5 条 |
| `depression_system.db` / `structured_assessments` | 15 | 14 | **1** | user 9 = 2 条 |
| `depression_system.db` / `physiological_records` | 6 | 6 | **0** | 每用户 1 条 |
| `depression_system.db` / `risk_assessments` | 31 | 15 | **3** | user 9 = 14 条 |
| `local_e2e.db` / 全部四表 | 0~13 | 0~13 | **0** | 每用户 1 条 |

部署形态：`backend/scripts/init_db.py` 只 `create_all()` + 引导默认租户，
**不灌任何 TextEntry / Assessment**（全仓 grep：写 `TextEntry` 的生产脚本不存在，
只有 `app/services/user_data_service.py:261` 的运行时写入与 tests）。

### 0.3 Gate 结论

**无真实纵向标注数据**（三条路径一致：部署形态、本地库、外部语料）。
更关键的是：即使 schema 支持，「同一用户多时点文本 **+ 发病时点标注**」这一监督信号
在本仓任何数据源里都不存在。

⇒ 本轮按提示词 §一 T2 走 **replay / 仿真基准** 路径。**所有读数必须显式标注
`synthetic`，禁止与任何真实指标同表并列。**

---

## 一、任务定义

**输入**：per-user 时序观测 `(t_1, x_1), …, (t_n, x_n)`，`x_t` 为该时点可得的观测
（本轮仿真基准中 = 一篇文本；`n` 因用户而异）。

**输出**：一个**报警时点** `d ∈ {1, …, n}` —— 系统决定"此用户需预警"的首个时点。
等价地也可输出 per-timestep 风险 + 停止策略。**若系统到序列结束都不报警，记 `d = n+1`。**

**参考标签**：`o` = 发病时点（onset），由**外部规则 + 真实 PHQ-9 分数**驱动，
**不由被评模型产出或自证**（见 §2.2）。

**为什么必须换指标**：普通 point-wise F1 把"漏掉前 3 篇后报警"与"第 1 篇就报警"
同等计分，完全抹掉早期检测的核心价值（延迟）。eRisk 口径把延迟直接写进罚项。

## 二、指标（eRisk 口径，本轮唯一权威口径）

记 `C` = 发病用户集合，`|C|` = 其规模；`T_i` = 用户 `i` 的序列长度；
`o_i` = onset 索引；`d_i` = 系统报警索引；`k` = 容忍窗口（本轮默认 50）。

### 2.1 ERDE@k（Early Risk Detection Error，eRisk 2018/2020 官方口径）

```
ERDE@k = (1/|C|) · Σ_{i∈C}  penalty_i(k)
penalty_i(k) = (o_i − d_i) / T_i    若 d_i ≤ o_i + k  （含提前报警）
             = 1                    否则（太晚或未报警）
```

关键性质：**提前报警（d_i < o_i）得负惩罚** —— 早发现是受奖励的，这正是 eRisk
对"早期"的计价方式。分母用 `T_i` 做长度归一，长序列的同等延迟代价更低。

实现注记（防歧义，代码按此落）：
- `o_i`、`d_i` 均为 **1-based**；
- 未报警（`d_i = n_i+1`）必然 > `o_i + k` ⇒ penalty = 1；
- 报告 ERDE50 为主读数，同时给 ERDE0/10/100 做敏感性表；
- **不 clamp 负值**（clamp 会抹掉"提前量"信息）；另出一版 clamped 变体做稳健性对照。

### 2.2 F_latency（latency-weighted F1，eRisk 2020 口径）

以 `latency_i = |o_i − d_i| / T_i` 作为用户级延迟罚因子，样本权重 `w_i = 1 − latency_i`：

```
P_latency = Σ_{i: alarmed} w_i        /  Σ_{i: alarmed and i∈C ∪ ¬C} w_i     （按实现细则见 2.3）
R_latency = Σ_{i∈C 且 alarmed} w_i   /  Σ_{i∈C} w_i
F_latency = 2 · P_latency · R_latency / (P_latency + R_latency)
```

### 2.3 计分细则（写死，防实现漂移）

| 情形 | 计入 |
|---|---|
| 发病用户且 `d_i ≤ o_i + k` | TP，权重 `w_i = 1 − latency_i` |
| 发病用户但太晚/未报警 | FN，权重 0（完全错过 ⇒ 无贡献） |
| 非发病用户但报警 | FP，权重 1（chaos：无 latency 概念，全额罚） |
| 非发病用户未报警 | TN，不参与 P/R |

### 2.4 禁止事项（铁律③）

**不得用普通 point-wise F1 冒充早期检测指标**。时点逐篇 F1 只作为"参照列"输出，
且表格中必须标注 `（非 eRisk 口径，仅参照）`。本轮判定门槛只用 ERDE@k 与 F_latency。

---

## 三、三档基线（全部实现，供对照）

| 档 | 名称 | 定义 |
|---|---|---|
| (a) | 现役时点范式 | per-timestep 独立二分类 + **固定阈值**；用户级 `d` = 首次越过阈值的时点 |
| (b) | 分层阈值 | per-timestep 概率 + 阈值随已观测时点收紧：`θ(t) = θ_0 − α·(t−1)`，本轮 `θ_0=0.55, α=0.02`（早松晚紧） |
| (c) | 学习式停止策略 | MLP over 累积表示（均值池化 + 时点计数 + 最后一步），直接优化 ERDE（见 §5） |

档 (a) 即现役生产的"逐时点打分 + 固定阈值"范式的等价物 —— **不是稻草人**，
它的劣势恰是本轮要量化的东西。

## 四、冻结口径与划分纪律（铁律①）

1. **按用户分组划分**：`StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=…)`，
   `groups = user_id`。**禁止同一用户的任何时点出现在 train 与 test 两侧** ——
   否则等于用未来观测训练去"预测"同一用户的过去（说话人泄漏，
   引 `2607.02920`：随机划分把 F1 虚高到 0.954）。
2. **特征侧零泄漏**：per-timestep 特征用**无状态哈希特征**
   （`HashingVectorizer` / 固定词表的字符 n-gram 哈希）。**禁止**用 TF-IDF：
   它会把全语料词频统计泄漏进 fold（与 B 轮 `git ls-files` 教训同源 ——
   任何跨 fold 的数据派生量都是泄漏）。
3. **标签侧零泄漏**：`o_i`（onset）只由 PHQ-9 分数序列 + 写死规则决定；
   特征提取**不接触** `phq9_score` / `phq9_binary` / `phq9_level`（L4 目标泄漏教训）。
4. **阈值不在评估集上选**（B.5 的 L3 教训）：基线 (a)/(b) 的阈值与档 (c) 的后验
   停止阈值都只在 **train 折**上选；test 折只报数。选参细节随代码落盘。
5. **随机种子固定**：划分、采样、模型初始化全部用同一 `random_state`，
   一键复现。

## 五、判定门槛（先定死）

在冻结口径下，档 (c) 相对档 (a)：

| 条件 | 结论 |
|---|---|
| `ERDE50(c) ≤ ERDE50(a)` **且** `F_latency(c) ≥ F_latency(a)` | 「有增量」⇒ 可进 T4 设计 |
| 任一方向不达标 | **如实立项阴性结论**，不自我说服加码（本轮边界） |

注意方向：ERDE **越低越好**，F_latency **越高越好**。

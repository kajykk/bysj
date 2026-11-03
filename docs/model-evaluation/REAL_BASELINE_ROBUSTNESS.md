# Depresjon 真实 actigraphy 基线的稳健性与佩戴混杂（ROUND_49）

> 本文件由 `backend/scripts/modeling/eval/v1_49/01_real_baseline_robustness.py` 生成。
> 只读离线评估，**没有修改生产模型、工件、阈值或运行时**。
> **这不是外部验证，也不是生产替换。**

## 0. 结论先行

- 18 个规范网格的受试者级 LOSO AUC：**0.5855–0.7364**（中位 0.6569）；95% CI 下界高于 0.5 的规范 10/18，覆盖 0.5 的 8/18。
- ROUND_48 的 0.6454 只是网格中的一个点；最好规范 mean__zero__all = 0.7364，最差规范 mean__nanmean__min14 = 0.5855。
- 零活动日比例单变量 AUC 0.3845，mean_act 单变量模型 AUC 0.5707，加入零活动日比例后 0.7133。
- 零活动日/活动分钟代理与标签相关，方向不一致：病例全零日更少，但活动日内的零活动分钟更多；**不能把信号解释为干净的生理效应**。
- 仅用佩戴代理的 LOSO 模型 AUC 0.7921，高于 ROUND_48 主口径 0.6454，也高于其多日聚合 0.7620；这是数据质量混杂的强信号。
- 记录时长也与标签相关：病例平均 15.6 个完整日，对照 20.9；`active_days` 与 `min14` 规范部分反映佩戴依从性，不是纯活动量。
- 结论：ROUND_48 的真实 actigraphy 信号是**脆弱的、与佩戴/活动模式纠缠的**；不升级证据等级，不进入生产，Phase 1 外部队列必须带佩戴元数据并预注册规则。
- **ROUND_50 后续审计（2026-11-02）**：ROUND_48 的日级多日聚合次口径（0.7620 ± 0.0093）另有 9 个规范：预注册 `day__zero__all` 精确复现，但受试者级 AUC 范围为 0.6565–0.7620，0.7620 是网格最大值；日级口径在 9/9 配对中高于本报告的受试者级 LOSO（差值 +0.0187 到 +0.0789），校准斜率 3.23–4.28。0.7620 也不是稳健单点引用；见 `docs/model-evaluation/REAL_BASELINE_PROTOCOL_ROBUSTNESS.md`。

## 1. 数据与设计

| 项目 | 值 |
|---|---|
| 受试者 | 55 |
| 完整日 | 1029（阳性日 359） |
| 全零完整日 | 70 |
| 非完整日（排除） | 115 |
| 规范网格 | 聚合 mean, median × 自相关处理 nanmean, zero, drop × 日纳入 all, nonzero, min14 = 18 个规范 |

- 分析单位：subject-level leave-one-subject-out; scaler fit inside each fold。
- Bootstrap：500 subject-level resamples, seed 42。
- 缺失处理：Autocorr modes: nanmean skips undefined days; zero fills them with 0 before aggregation; drop removes the feature. Day modes: all complete days; nonzero excludes all-zero days; min14 keeps subjects with at least 14 complete days.

## 2. 规范曲线

| 规范 | 特征数 | 受试者 | 日 | AUC | 95% CI | Brier |
|---|---:|---:|---:|---:|---|---:|
| `mean__nanmean__all` | 4 | 55 | 1029 | 0.6454 | [0.4939, 0.7985] | 0.2232 |
| `mean__nanmean__nonzero` | 4 | 55 | 959 | 0.6739 | [0.5291, 0.8190] | 0.2201 |
| `mean__nanmean__min14` | 4 | 51 | 978 | 0.5855 | [0.4092, 0.7655] | 0.2348 |
| `mean__zero__all` | 4 | 55 | 1029 | 0.7364 | [0.6017, 0.8653] | 0.2003 |
| `mean__zero__nonzero` | 4 | 55 | 959 | 0.6848 | [0.5402, 0.8291] | 0.2145 |
| `mean__zero__min14` | 4 | 51 | 978 | 0.6823 | [0.5201, 0.8371] | 0.2095 |
| `mean__drop__all` | 3 | 55 | 1029 | 0.6793 | [0.5411, 0.8394] | 0.2198 |
| `mean__drop__nonzero` | 3 | 55 | 959 | 0.6916 | [0.5455, 0.8408] | 0.2175 |
| `mean__drop__min14` | 3 | 51 | 978 | 0.6194 | [0.4596, 0.7820] | 0.2315 |
| `median__nanmean__all` | 4 | 55 | 1029 | 0.6793 | [0.5216, 0.8232] | 0.2205 |
| `median__nanmean__nonzero` | 4 | 55 | 959 | 0.6427 | [0.4914, 0.7894] | 0.2293 |
| `median__nanmean__min14` | 4 | 51 | 978 | 0.6306 | [0.4625, 0.7790] | 0.2315 |
| `median__zero__all` | 4 | 55 | 1029 | 0.6576 | [0.5191, 0.7949] | 0.2319 |
| `median__zero__nonzero` | 4 | 55 | 959 | 0.6386 | [0.4876, 0.7873] | 0.2310 |
| `median__zero__min14` | 4 | 51 | 978 | 0.5952 | [0.4486, 0.7497] | 0.2423 |
| `median__drop__all` | 3 | 55 | 1029 | 0.6821 | [0.5438, 0.8169] | 0.2280 |
| `median__drop__nonzero` | 3 | 55 | 959 | 0.6562 | [0.5124, 0.7952] | 0.2361 |
| `median__drop__min14` | 3 | 51 | 978 | 0.6177 | [0.4628, 0.7764] | 0.2383 |

### 2.1 因子汇总

| 因子 | 水平 | 规范数 | AUC 均值 | AUC 最小 | AUC 最大 |
|---|---|---:|---:|---:|---:|
| 聚合 | mean | 9 | 0.6665 | 0.5855 | 0.7364 |
| 聚合 | median | 9 | 0.6445 | 0.5952 | 0.6821 |
| 自相关处理 | drop | 6 | 0.6577 | 0.6177 | 0.6916 |
| 自相关处理 | nanmean | 6 | 0.6429 | 0.5855 | 0.6793 |
| 自相关处理 | zero | 6 | 0.6658 | 0.5952 | 0.7364 |
| 日纳入 | all | 6 | 0.6800 | 0.6454 | 0.7364 |
| 日纳入 | min14 | 6 | 0.6218 | 0.5855 | 0.6823 |
| 日纳入 | nonzero | 6 | 0.6646 | 0.6386 | 0.6916 |

`mean__nanmean__all` 的点估计与 ROUND_48 主口径相同（0.6454）；本表 CI 由 500 次 bootstrap 得到，ROUND_48 用 2000 次，故区间端点略有差异。

最敏感的两个选择是**自相关缺失处理**和**日纳入规则**：把未定义自相关填 0 的平均 AUC 最高（0.6658 vs nanmean 0.6429、drop 0.6577）；限制 ≥14 天后平均 AUC 最低（0.6218），剔除零活动日的影响方向不一致（均值 0.6646，但部分规范上升、部分下降）。这说明 ROUND_48 的 0.6454 不是稳健点估计。

18 个规范共享同一批 55 名受试者，不是独立样本；范围描述的是**分析选择敏感性**，不是抽样分布。`autocorr_mode=drop` 同时改变缺失处理与特征数（4→3），因此该因子的汇总不能单独解释为「删掉自相关特征」的效应。各规范的校准斜率范围 0.344–1.014，在 55 人样本上不足以形成校准结论。

主口径仍是 ROUND_48 预注册的 `mean__nanmean__all`（0.6454）；其余 17 个规范只用于报告敏感性，**不得事后挑选最大值 0.7364 作为性能估计**。

## 3. 零活动日与佩戴代理

### 3.1 单变量读数（受试者级，4 特征主口径的受试者表）

| 变量 | AUC（原始方向） | AUC（定向） | 方向 | 病例均值 | 对照均值 | Mann-Whitney p |
|---|---:|---:|---|---:|---:|---:|
| `mean_act` | 0.3519 | 0.6481 | higher value -> control | 166.0933 | 210.6296 | 0.0641 |
| `zero_day_fraction` | 0.3845 | 0.6155 | higher value -> control | 0.0108 | 0.0636 | 0.0460 |
| `mean_active_minutes` | 0.3573 | 0.6427 | higher value -> control | 815.5133 | 890.5611 | 0.0746 |
| `mean_zero_minutes` | 0.6427 | 0.6427 | higher value -> condition | 624.4867 | 549.4389 | 0.0746 |
| `active_mean_act` | 0.3111 | 0.6889 | higher value -> control | 167.0777 | 221.4700 | 0.0181 |
| `active_days` | 0.2656 | 0.7344 | higher value -> control | 15.3913 | 18.9062 | 0.0022 |

`mean_zero_minutes` 与 `mean_active_minutes` 互补（合计 1440 分钟），两者不是独立证据；6 个单变量检验未做多重比较校正，p 值只作描述。

分组分布：病例 2 人有全零日（共 5 天），对照 10 人有全零日（共 65 天）。

记录时长本身也与标签相关：病例平均 15.6 个完整日（中位 14.0），对照平均 20.9（中位 18.5）。`active_days` 的差异（病例 15.4 vs 对照 18.9）至少部分是记录时长/佩戴依从性差异；`min14` 规范因此同时改变样本构成，不能当作纯质量过滤。

### 3.2 多变量 LOSO 模型

| 模型 | 特征 | AUC | 95% CI | Brier | 系数方向（负向折数） |
|---|---|---:|---|---:|---|
| mean_act_only | mean_act | 0.5707 | [0.4132, 0.7421] | 0.2427 | `mean_act` -0.530 (55/55 折为负) |
| zero_day_fraction_only | zero_day_fraction | 0.3003 | [0.1422, 0.4591] | 0.2386 | `zero_day_fraction` -0.738 (55/55 折为负) |
| mean_active_minutes_only | mean_active_minutes | 0.5272 | [0.3646, 0.6874] | 0.2571 | `mean_active_minutes` -0.279 (55/55 折为负) |
| active_mean_act_only | active_mean_act | 0.6440 | [0.4871, 0.7947] | 0.2316 | `active_mean_act` -0.694 (55/55 折为负) |
| mean_act_plus_zero_fraction | mean_act, zero_day_fraction | 0.7133 | [0.5820, 0.8452] | 0.2088 | `mean_act` -0.846 (55/55 折为负); `zero_day_fraction` -1.048 (55/55 折为负) |
| mean_act_plus_active_minutes | mean_act, mean_active_minutes | 0.5408 | [0.3874, 0.7074] | 0.2521 | `mean_act` -0.498 (55/55 折为负); `mean_active_minutes` -0.073 (54/55 折为负) |
| wear_proxies_only | zero_day_fraction, mean_active_minutes, active_days | 0.7921 | [0.6498, 0.9103] | 0.1960 | `zero_day_fraction` -1.054 (55/55 折为负); `mean_active_minutes` -0.844 (55/55 折为负); `active_days` -0.588 (55/55 折为负) |
| mean_act_plus_wear_proxies | mean_act, zero_day_fraction, mean_active_minutes | 0.7745 | [0.6239, 0.8950] | 0.1909 | `mean_act` -0.691 (55/55 折为负); `zero_day_fraction` -1.404 (55/55 折为负); `mean_active_minutes` -0.709 (55/55 折为负) |

单特征 LOSO 模型 AUC 与 §3.1 的单变量 AUC 不必相等：每折标准化参数与截距不同，把各折的 out-of-fold 概率拼起来后，跨折排序会改变。两者只用于方向一致性检查，不能互相替代。

`zero_day_fraction` 与 `mean_active_minutes` / `active_days` 是**数据质量/佩戴代理**，不是临床特征；把它们加入模型只能说明信号与这些代理纠缠，不能说明模型可用。

### 3.3 相关性

| 变量对 | Spearman ρ | p |
|---|---:|---:|
| `zero_day_fraction__mean_act` | -0.3345 | 0.0126 |
| `mean_active_minutes__mean_act` | 0.5219 | 0.0000 |
| `mean_zero_minutes__mean_act` | -0.5219 | 0.0000 |
| `zero_day_fraction__active_mean_act` | -0.1775 | 0.1948 |

### 3.4 全零日最多的受试者

| 受试者 | 标签 | 完整日 | 全零日 |
|---|---:|---:|---:|
| `control_3` | 0 | 45 | 20 |
| `control_32` | 0 | 34 | 14 |
| `control_31` | 0 | 34 | 13 |
| `control_1` | 0 | 34 | 5 |
| `condition_20` | 1 | 17 | 3 |
| `control_17` | 0 | 19 | 3 |
| `control_21` | 0 | 21 | 3 |
| `condition_16` | 1 | 28 | 2 |

全零日集中在少数对照受试者，且病例在活动日内有更多零活动分钟；没有佩戴/非佩戴标志时，无法区分「完全不活动」「设备未戴」和「睡眠/休息」。

### 3.5 排除高零活动日受试者

| 模型 | 全部 | 排除 control_3 | 排除 control_32 | 排除 control_31 | 排除三者 |
|---|---:|---:|---:|---:|---:|
| primary4_mean_nanmean | 0.6454 | 0.6396 | 0.6550 | 0.6424 | 0.6462 |
| best_mean_zero | 0.7364 | 0.7279 | 0.7279 | 0.7279 | 0.7091 |
| wear_proxies_only | 0.7921 | 0.7868 | 0.7868 | 0.7868 | 0.7751 |
| primary4_plus_wear | 0.7677 | 0.7602 | 0.7616 | 0.7602 | 0.7451 |

排除对象按全零日数预先指定（control_3、control_32、control_31 为全零日最多的三名受试者）。排除后主口径仍在 0.640–0.655，佩戴代理模型仍在 0.775–0.792；最好规范从 0.7364 降到 0.7091，仍落在网格范围内。结论不是由单一受试者驱动，但也不能消除佩戴混杂。

## 4. 解释边界

**允许的表述**

- 在 Depresjon 上，真实 actigraphy 的受试者级 AUC 对可辩护的聚合方式与日纳入规则敏感。
- 零活动日与活动分钟代理与标签相关，因此该基线不能当作干净的生理信号。
- ROUND_49 不提升生产生理单元的证据等级，也不修改任何工件。

**禁止的表述**

- ROUND_48 的 0.6454 或 0.7620 是稳定的真实生理性能估计。
- 真实 actigraphy 基线已获外部验证或已可用于生产。
- 佩戴代理模型具有临床意义；它们只是数据质量与活动模式的诊断。
- 这些结果适用于消费级可穿戴、普通成人或临床诊断。

## 5. 复现

```bash
cd backend
.venv/Scripts/python.exe scripts/modeling/eval/v1_49/01_real_baseline_robustness.py
```

- 规范明细：`backend/scripts/modeling/eval/v1_49/specification_curve.csv`。
- JSON：`backend/scripts/modeling/eval/v1_49/robustness_audit.json`；镜像：`outputs/candidates/round49/robustness_audit.json`。
- 全部随机过程固定 seed=42；bootstrap 500 次。

## 6. 对 Phase 1 的含义

1. 真实 actigraphy 的 ROUND_48 读数不能作为稳定性能估计；外部评估必须同时报告规范曲线，而不是只报一个最佳数字。
2. 外部队列必须提供佩戴/非佩戴或有效佩戴时长；没有它，零活动日与疾病活动度无法分离。
3. 处理规则（自相关缺失、零活动日、聚合方式）应在看外部标签前预注册，否则规范选择本身会变成隐性调参。
4. 这些结果仍不支持普通人群、消费级可穿戴或临床诊断用途，也不改变生产单元证据等级。

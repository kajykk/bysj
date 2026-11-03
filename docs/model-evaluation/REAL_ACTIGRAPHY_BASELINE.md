# Depresjon 真实 actigraphy 分组基线（ROUND_48）

> 本文件由 `backend/scripts/modeling/eval/v1_48/01_real_actigraphy_baseline.py` 生成。
> 只读离线评估，**没有修改生产模型、工件、阈值或运行时**。
> **这不是外部验证，也不是生产替换。**
>
> **ROUND_49 更新（2026-11-02）**：本报告的 0.6454 对分析规范敏感
> （18 个规范的受试者级 LOSO AUC 为 0.5855–0.7364），且与零活动日/记录时长代理纠缠
> （仅佩戴代理的 LOSO AUC 为 0.7921）。引用本报告前必须同时阅读
> `docs/model-evaluation/REAL_BASELINE_ROBUSTNESS.md`；0.6454 不是稳健性能估计。
>
> **ROUND_50 更新（2026-11-02）**：多日聚合次口径的 0.7620 也已做 9 规范审计；
> 预注册规范精确复现，但 9 规范受试者级 AUC 为 0.6565–0.7620，0.7620 是网格最大值，
> 不是稳健协议估计；日级与受试者级 LOSO 回答不同问题，不能互相替代。见
> `docs/model-evaluation/REAL_BASELINE_PROTOCOL_ROBUSTNESS.md`。

## 0. 结论先行

- 数据：55 名受试者（23 例 / 32 对照），1029 个完整日；排除 115 个非 1440 分钟日。
- 保守主口径（受试者均值 + LOSO，4 个真实特征）：AUC **0.6454** [0.4861, 0.7983]，Brier 0.2232；置换检验 p=0.0240。
- 多日聚合次口径（日级分组 CV + 受试者聚合，4 个真实特征）：受试者级 AUC **0.7620 ± 0.0093**，合并 OOF 为 0.7636；置换检验 p=0.0020。
- 两个口径不一致，说明估计依赖「是否把同一天的预测聚合成多日平均」；不能只挑其中较大的一个对外报告。
- 真实 actigraphy 在本队列有可检出的组间信号（两种受试者级口径均高于 0.5）；生产 MLP 的 0.9451 是合成特征读数，特征来源、标签与协议不同，不能并列比较。

## 1. 数据与来源

| 项目 | 值 |
|---|---|
| 原始压缩包 | `datasets/external/physiological/depresjon-code/depresjon.zip` |
| ZIP SHA-256 | `ef588952113c943af549243adf459cc4ba59b9b01990e5323b9c73819553f532` |
| TDF_CONDITION SHA-256 | `c99d40b4171ee6ce98c470b98bf3f464c25d9310e933ac3c094409d3add84cf8` |
| TDF_CONTROL SHA-256 | `d138e90b1e8cf2d4e7bca0a40579499a5288dd3ded43fa77ff8133d8f84b28c9` |
| 受试者 | 55（23 例 / 32 对照） |
| 完整日 | 1029；阳性日 359（0.3489） |
| 受试者天数 | 12–45（中位 15） |
| 非完整日（排除） | 115 |
| 全零完整日 | 70 |
| 标签来源 | raw file directory: data/condition/* vs data/control/* |
| 许可 | The in-repo depresjon-code LICENSE is MIT and covers the code repository; the Depresjon data itself has no separate license file in this repository, so redistribution/citation must follow the original dataset terms. |

### 1.1 与 TDF 的一致性校验

- TDF 共 1029 行；按「日期 + mean_act + peak_activity」唯一匹配 996 行；键重复但候选值一致的歧义行 33 行；完全未匹配 0 行。
- 歧义行中全零日 31 行，来自 control_1/31/32 的共享零活动日；另有 2 行是 control_6/control_7 在 2003-04-12 的完全相同日；全部候选特征/标签一致：True。
- 匹配行标签冲突：0。
- `mean_act` 最大绝对差 5.684e-14；`std_act` 7.958e-13；`peak_activity` 0.000e+00；`autocorrelation_act` 1.577e-14 （951 行可比）。
- TDF rows do not carry subject IDs. 996/1029 rows match one raw day uniquely on date + mean + peak. The remaining 33 TDF rows share their key with 2-3 raw days: 31 are all-zero days from control_1/31/32, and 2 are the identical control_6/control_7 rows on 2003-04-12. All ambiguous candidates have identical feature values and labels, so the raw per-subject files (which retain the subject ID for all 1029 complete days) remain the source of truth; TDF is only a definition check.

## 2. 特征与评估设计

- 主特征（4 个）：`mean_act`, `std_act`, `peak_activity`, `autocorrelation_act`。
- 探索特征（10 个）：`mean_act`, `std_act`, `peak_activity`, `autocorrelation_act`, `rms_act`, `skewness_act`, `kurtosis_act`, `shape_factor_act`, `crest_factor_act`, `impulse_factor_act`。
- 缺失处理：autocorrelation is undefined on constant days (78 days). Day-level models fill it with 0.0; subject-mean models average available values and fill an all-missing subject with 0.0.
- 主口径：Aggregate each subject's complete days to the mean of the four real features, then leave one subject out; scaler and logistic regression fit on the other 54 subjects only.
- 次口径：Train a day-level logistic regression with 5-fold StratifiedGroupKFold (subjects never split across folds), repeat 10 times, then average held-out day probabilities per subject.
- 泄漏对照：Same 5-fold repeated CV but with StratifiedKFold on days, which lets days from one subject appear in both train and test; used only to quantify optimism from subject leakage.
- Bootstrap：2000 subject-level resamples, seed 42；置换：500 subject-label permutations, seed 42

## 3. 结果

| 口径 | 分析单位 | n | AUC | 95% CI / 重复 SD | AUPRC | Brier | 平均预测 |
|---|---|---:|---|---:|---:|---:|---:|
| 主口径：受试者均值 LOSO，4 特征 | 受试者 | 55 | 0.6454 | [0.4861, 0.7983] | 0.6573 | 0.2232 | 0.4209 |
| 次口径：日级分组 + 多日聚合，4 特征 | 受试者 | 55 | 0.7620 | ±0.0093（重复） | 0.7521 | 0.2216 | 0.3560 |
| 次口径的日级读数 | 日 | 1029 | 0.6575 ± 0.0057 | — | 0.4288 | 0.2177 | — |
| 探索：受试者均值 LOSO，10 特征 | 受试者 | 55 | 0.7568 | [0.6036, 0.8902] | 0.7905 | 0.1896 | 0.4225 |
| 探索：日级分组 + 多日聚合，10 特征 | 受试者 | 55 | 0.7989 | ±0.0091（重复） | 0.8224 | 0.2101 | 0.3629 |

日级 AUC 把同一天的预测当作独立样本，只用于描述；受试者级读数是主分析单位。受试者级 AUC 的重复 SD 反映 10 次分组切分的波动，不是 95% CI。合并 OOF（10 次重复的平均预测）AUC：4 特征 0.7636，10 特征 0.8030。

### 3.1 受试者级置换检验

- 主口径 LOSO：观测 AUC 0.6454，500 次受试者标签置换的均值 0.4131，单侧 p=0.0240。
- 次口径多日聚合：观测 AUC 0.7620，500 次受试者标签置换的均值 0.5016，单侧 p=0.0020。
- 置换检验只说明「在该队列内，观测到的排序不太可能由标签随机置换产生」；不等于外部泛化或临床可用。

### 3.2 泄漏对照

| 协议 | 日级 AUC（重复均值） | 受试者级 AUC（重复均值） |
|---|---:|---:|
| 分组 CV（4 特征） | 0.6575 ± 0.0057 | 0.7620 ± 0.0093 |
| 非分组行级 CV（4 特征） | 0.6683 ± 0.0020 | 0.7791 ± 0.0048 |

非分组 CV 让同一受试者的不同天同时进入训练和测试，理论上应更乐观。本数据上差距不大，但不能因此认为行级切分可接受：它仍然把同一个人当作独立样本，会低估不确定性。此前来源审计的 0.6443 用的是 2 个真实派生列和行级 5 折，与本表的 4 个原始特征/分组协议不可直接比较。

### 3.3 单变量信号

| 受试者均值特征 | AUC（方向未翻转） | 翻转后 AUC | 方向 |
|---|---:|---:|---|
| `mean_act` | 0.3519 | 0.6481 | higher value -> lower label |
| `std_act` | 0.4239 | 0.5761 | higher value -> lower label |
| `peak_activity` | 0.4851 | 0.5149 | higher value -> lower label |
| `autocorrelation_act` | 0.5326 | 0.4674 | higher value -> higher label |

`mean_act` 的方向最明确：活动均值越低，越偏向抑郁组。单变量 AUC 不等于多变量模型，也不能解释为因果。

### 3.4 阈值行为（受试者级，多日聚合口径）

| 阈值 | 灵敏度 | 特异度 | PPV | NPV | 告警率 | TP/FP/FN/TN |
|---:|---:|---:|---:|---:|---:|---|
| 0.30 | 0.913 | 0.312 | 0.488 | 0.833 | 0.782 | 21/22/2/10 |
| 0.35 | 0.696 | 0.625 | 0.571 | 0.741 | 0.509 | 16/12/7/20 |
| 0.40 | 0.565 | 0.906 | 0.812 | 0.744 | 0.291 | 13/3/10/29 |
| 0.50 | 0.043 | 1.000 | 1.000 | 0.593 | 0.018 | 1/0/22/32 |

阈值表是描述性的，没有做阈值选择或重新校准。多日聚合模型的平均预测明显低于实际阳性率，0.50 阈值几乎不报警；0.35 附近的灵敏度/特异度只是该队列上的观测，不能直接搬到别的队列。

### 3.5 校准与严重度

- 主口径 Brier 0.2232，ECE(5 bin) 0.0498，校准斜率 0.825。
- 次口径 Brier 0.2216，ECE(5 bin) 0.1577，校准斜率 4.054。
- 在 23 名病例中，多日聚合分数与 MADRS-1 的 Spearman ρ=0.010（p=0.962），与 MADRS-2 ρ=0.045（p=0.838）。
- 这说明该基线主要区分病例/对照，**没有**证据表明它能跟踪症状严重度；校准也未达到可用于个体风险沟通的程度。

### 3.6 敏感性

| 口径 | 受试者 | 日 | 受试者级 AUC | Brier |
|---|---:|---:|---:|---:|
| 全部完整日（主分析） | 55 | 1029 | 0.7620 ± 0.0093 | 0.2216 |
| 排除全零日 | 55 | 959 | 0.7091 ± 0.0136 | 0.2259 |
| 仅保留 ≥14 个完整日的受试者 | 51 | 978 | 0.7010 ± 0.0196 | 0.2251 |

排除全零日或剔除天数过少的受试者后，多日聚合 AUC 下降约 0.05–0.06，说明结果部分依赖零活动日/佩戴天数；没有佩戴或非佩戴标志，无法把「完全不活动」与「设备未戴」分开。这是本基线的主要数据质量限制。

### 3.7 人口学负对照

- 仅用性别 + 年龄组中点的受试者级 LOSO AUC 0.5476，Brier 0.2490。
- 这不是一个可部署模型，只用于说明 actigraphy 的读数不是由年龄/性别单独解释；样本仅 55 人，不能做正式混杂校正。

## 4. 解释边界

**允许的表述**

- 「在 Depresjon 的 55 名受试者上，按受试者分组的真实 actigraphy 基线达到上述 AUC；它明显低于合成特征生产模型的 0.9451。」
- 「保守的受试者均值 LOSO 与多日聚合估计不一致；两者都应报告，不能把较大的一个当作稳定性能。」
- 「主要单变量信号是较低的活动均值；该基线没有显示 MADRS 严重度跟踪能力。」

**禁止的表述**

- 「这是外部验证」或「可以用于普通成人/消费级可穿戴」。
- 「真实 actigraphy 的 AUC 是 0.76，所以生产模型可以换成它」——这是离线基线，没有外部验证、没有校准、没有阈值验证。
- 「0.762 可以和生产模型 0.9451 比较」——特征来源、标签和协议不同。
- 「10 特征探索模型应该上线」——55 人、单一队列、没有外部队列。

## 5. 复现

```bash
cd backend
.venv/Scripts/python.exe scripts/modeling/eval/v1_48/01_real_actigraphy_baseline.py
```

- 全部随机过程固定 seed=42；bootstrap 2000 次；置换 500 次。
- 受试者级预测明细：`backend/scripts/modeling/eval/v1_48/subject_predictions.csv`。
- JSON：`backend/scripts/modeling/eval/v1_48/real_actigraphy_baseline.json`；镜像：`outputs/candidates/round48/real_actigraphy_baseline.json`。

## 6. 对 Phase 1 的含义

1. 真实 actigraphy 确实有信号，但当前证据只能支持「同队列、按人分组、回顾性」的有限读数；不能升级运行时生理单元的 `synthetic_label_derived` 等级。
2. 生产生理模型若要用真实特征重建，应以本脚本的受试者分组协议为最低门槛，并补外部队列、校准集与佩戴/非佩戴处理。
3. 多日聚合与单日/受试者均值的结果差异必须保留在报告中，不能只留一个好看的数字。
4. 在该队列之外，没有任何证据支持普通人群、消费级设备或临床诊断用途。

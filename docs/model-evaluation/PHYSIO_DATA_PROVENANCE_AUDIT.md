# 生理训练数据来源审计：processed Depresjon 的 7 列特征何来

> **结论先说：`depresjon_physiological.csv` 的 8 个建模列可以由
> `scripts/data_prep/convert_depresjon_to_system.py` 逐行逐值复现（seed=42，8/8 列完全相等）。
> 其中 5 个原始特征由「真实队列标签」驱动生成，另 1 个由这 5 个之一派生；
> 只有 `steps` 与 `exercise_minutes` 来自真实 actigraphy 汇总。
> 因此当前生理模型的 AUC/F1 **不能**解释为「从真实生理信号识别抑郁」的能力。**
>
> 本审计只读、不训练、不改工件、不改阈值。审计日期 2026-11-02。

## 1. 审计对象

| 项 | 值 |
|---|---|
| 训练 CSV | `datasets/physiological/external/depresjon_processed/depresjon_physiological.csv`（1,029 行） |
| 生成脚本 | `scripts/data_prep/convert_depresjon_to_system.py` |
| 原始输入 | `datasets/external/physiological/depresjon-code/TDF_CONDITION.csv`（359 行）+ `TDF_CONTROL.csv`（670 行） |
| 训练消费者 | `backend/app/ml/data_loader.py::load_depresjon_data` |
| 当前工件 | `backend/models/artifacts/physiological_optimized/`（v2 MLP，13 特征） |

## 2. 复现证据

按生成脚本的原始顺序（`concat([condition, control])`，`np.random.seed(42)`）重新生成 8 列，
与仓内 CSV 逐值比较：

| 列 | 生成公式（脚本原文） | 与仓内 CSV 相等比例 | 最大绝对差 |
|---|---|---:|---:|
| `steps` | `mean_act * 10 + N(0, 500)`，clip 1000–20000 | 1.0000 | 0 |
| `heart_rate` | 组均值 68/78 + `N(0, 8)`，clip 50–120 | 1.0000 | 0 |
| `sleep_hours` | 组均值 7.5/5.5 + `N(0, 1)`，clip 3–10 | 1.0000 | 0 |
| `sleep_quality` | 组均值 4/2 + `N(0, 0.8)`，clip 1–5 | 1.0000 | 0 |
| `exercise_minutes` | `peak_activity / 50 + N(0, 10)`，clip 0–120 | 1.0000 | 0 |
| `systolic_bp` | 组均值 115/125 + `N(0, 10)`，clip 90–160 | 1.0000 | 0 |
| `diastolic_bp` | `systolic_bp * 0.65 + N(0, 5)`，clip 60–100 | 1.0000 | 0 |
| `depression_label` | `Label == "condition"` | 1.0000 | 0 |
| `phq9_score` | 组均值 5/15 + `N(0, 3)`，clip 0–27 | 1.0000 | 0 |

复跑（只读，不写文件）：

```bash
cd backend
.venv/Scripts/python.exe - <<'PY'
import pandas as pd, numpy as np
from pathlib import Path
base = Path('../datasets/external/physiological/depresjon-code')
combined = pd.concat([pd.read_csv(base/'TDF_CONDITION.csv'),
                      pd.read_csv(base/'TDF_CONTROL.csv')], ignore_index=True)
np.random.seed(42)
synth = {
    'steps': (combined['mean_act']*10 + np.random.normal(0,500,len(combined))).clip(1000,20000).astype(int),
    'heart_rate': (np.where(combined['Label']=='condition',78,68) + np.random.normal(0,8,len(combined))).clip(50,120).astype(int),
    'sleep_hours': (np.where(combined['Label']=='condition',5.5,7.5) + np.random.normal(0,1,len(combined))).clip(3,10).round(1),
    'sleep_quality': (np.where(combined['Label']=='condition',2,4) + np.random.normal(0,0.8,len(combined))).clip(1,5).astype(int),
    'exercise_minutes': (combined['peak_activity']/50 + np.random.normal(0,10,len(combined))).clip(0,120).astype(int),
}
sys = (np.where(combined['Label']=='condition',125,115) + np.random.normal(0,10,len(combined))).clip(90,160).astype(int)
synth['systolic_bp'] = sys
synth['diastolic_bp'] = (sys*0.65 + np.random.normal(0,5,len(combined))).clip(60,100).astype(int)
synth['depression_label'] = (combined['Label']=='condition').astype(int)
cur = pd.read_csv('../datasets/physiological/external/depresjon_processed/depresjon_physiological.csv')
for k, v in synth.items():
    print(k, float(np.mean(v == cur[k].to_numpy())))
PY
```

## 3. 特征来源判定

| 特征 | 来源 | 是否携带标签信息 | 说明 |
|---|---|---|---|
| `steps` | 真实 `mean_act` × 10 + 噪声 | 弱（相关 −0.156） | 唯一接近真实活动量的列，但量纲是人为放大 |
| `exercise_minutes` | 真实 `peak_activity` / 50 + 噪声 | 几乎无（相关 +0.022） | 真实活动峰值的事后缩放 |
| `heart_rate` | 标签分组均值 68/78 + 噪声 | **强（相关 +0.512）** | 由 `Label` 决定均值 |
| `sleep_hours` | 标签分组均值 7.5/5.5 + 噪声 | **强（相关 −0.701）** | 由 `Label` 决定均值 |
| `sleep_quality` | 标签分组均值 4/2 + 噪声 | **强（相关 −0.735）** | 由 `Label` 决定均值 |
| `systolic_bp` | 标签分组均值 115/125 + 噪声 | **强（相关 +0.420）** | 由 `Label` 决定均值 |
| `diastolic_bp` | `systolic_bp × 0.65` + 噪声 | **强（相关 +0.338）** | 继承 `systolic_bp` 的标签信息 |
| `phq9_score` | 标签分组均值 5/15 + 噪声 | **强（相关 +0.843）** | **不是真实 PHQ-9**，是标签的噪声副本 |

13 个模型输入中，9 个直接或间接来自上述标签驱动列：
`sleep_hours`、`sleep_quality`、`heart_rate`、`systolic_bp`、`diastolic_bp`、
`sleep_efficiency`、`cardiovascular_risk`、`hr_sleep_interaction`、`bp_category`。
只有 `steps`、`exercise_minutes`、`activity_intensity`、`overall_activity` 来自真实 actigraphy 汇总。

## 4. 对指标的影响（仅作口径说明，不是新模型）

在同一份 1,029 行数据上，用 5 折分层 OOF 的逻辑回归做「特征集消融」：

| 输入特征集 | 5 折 OOF AUC |
|---|---:|
| 仅真实 actigraphy 派生列（`steps` + `exercise_minutes`） | **0.6443** |
| 仅标签驱动合成列（5 列） | **0.9898** |
| 全部 7 列 | **0.9901** |
| 当前 MLP v2（固定 test n=157，生产口径） | 0.9451 |

读法：

1. 真实 actigraphy 汇总列只能给出 AUC 0.644 级信号；
2. 合成列单独就能给出 0.990 级信号，因为它们的组均值直接写入了标签；
3. 当前 MLP 的 0.9451 落在合成列的可解释范围内，**不能**作为「真实生理信号可识别抑郁」的证据；
4. 0.9451 仍可作为「生产管线的一致性/回归读数」，但必须同时标注特征来源。

## 5. 仍然有效与不再有效

**仍然有效**

- `depression_label` 来自真实 Depresjon 队列的 condition/control 划分；
- `steps` / `exercise_minutes` 的母体 `mean_act` / `peak_activity` 是真实 actigraphy 汇总；
- 固定切分、train-only cleaner/scaler、逐样本可复现等工程结论；
- 当前工件可以继续用于接口联调、回归测试和管线演示。

**不再有效**

- 把 0.9451 / 0.8205 解读为「生理信号抑郁识别性能」；
- 把该模型称为「临床活动记录队列上的生理模型」而不提合成特征；
- 用该模型的外部迁移失败/成功推断真实可穿戴设备的可用性；
- 在论文、答辩、项目介绍中把该 AUC 与结构化/文本模型的能力并列比较。

## 6. 修复路径（Phase 1 的输入）

1. **优先用原始 actigraphy 特征重做生理基线**：`mean_act` / `std_act` / `peak_activity` /
   `autocorrelation` 等真实汇总列 + 真实标签，重新切分、重新训练；当前 7 列 synthetic
   schema 不再作为真实生理模型的特征表。
   **ROUND_48（2026-11-02）已执行同队列版本**：回到 `depresjon.zip` 的逐受试者分钟级数据，
   55 受试者 / 1,029 完整日，受试者分组。主口径（受试者均值 + LOSO）AUC 0.6454
   [0.4861, 0.7983]；多日聚合次口径 0.7620 ± 0.0093；排除全零日后 0.7091。
   注意与上表 0.6443 的区别：0.6443 是「steps + exercise 两列 + 行级 5 折」，
   0.6454 是「4 个原始汇总特征 + 受试者均值 LOSO」，数值接近但口径不同。
   该基线仍不是外部验证，不改变生产工件、阈值或证据等级。
   报告：`REAL_ACTIGRAPHY_BASELINE.md`；脚本：`backend/scripts/modeling/eval/v1_48/01_real_actigraphy_baseline.py`。
   **ROUND_49（2026-11-02）稳健性审计**：18 个规范网格的受试者级 LOSO AUC 为
   0.5855–0.7364（中位 0.6569），0.6454 不是稳健点估计；仅用零活动日/活动分钟/记录天数
   代理的 LOSO AUC 0.7921，病例平均 15.6 个完整日 vs 对照 20.9。该信号与佩戴/记录时长
   纠缠，不能解释为干净的生理效应。报告：`REAL_BASELINE_ROBUSTNESS.md`。
   **ROUND_50（2026-11-02）多日聚合规范审计**：日级 9 规范（自相关 zero/mean/drop ×
   日纳入 all/nonzero/min14）的受试者级 AUC 为 0.6565–0.7620；预注册 `day__zero__all`
   精确复现 0.7620 ± 0.0093，但它是网格最大值，不是稳健协议估计；日级与受试者级 LOSO
   回答不同问题。报告：`REAL_BASELINE_PROTOCOL_ROBUSTNESS.md`。
2. **外部成人队列**：NHANES 2017–2018 有实测血压/脉搏/睡眠时长 + PHQ-9，可作为
   「真实特征 + 量表标签」的外部压力测试；但它没有 actigraphy 步数，且标签是 PHQ-9≥10，
   与 Depresjon 的临床分组不同，只能作迁移压力测试，不能与当前 AUC 直接比较。
   **ROUND_47（2026-11-02）已执行**：生产默认填充 n=5,068，AUC 0.5459 [0.5163, 0.5754]，
   平均预测 0.471 vs 实际阳性率 0.091，校准斜率 0.2114，ECE 0.3804；完整 6 特征 n=3,410
   AUC 0.5505。该读数只说明当前管线没有可用的跨队列迁移证据，不能归因于真实生理信号能力。
   报告：`NHANES_TRANSPORT_STRESS.md`；脚本：`backend/scripts/modeling/eval/v1_47/01_nhanes_transport_stress.py`。
3. **任何新读数必须同时登记**：特征来源（真实/合成/代理）、标签来源、人群、
   采集协议、是否参与训练；缺一项不得进入论文或对外材料。

## 7. 关联文档

- `docs/model-evaluation/POPULATION_EVIDENCE_MATRIX.md` §2.3（生理证据等级已下调）、§2.5（NHANES 压力测试）、§2.6（ROUND_48 真实基线）、§2.7（ROUND_49 稳健性）、§2.8（ROUND_50 多日聚合规范）
- `docs/model-evaluation/MODEL_CARD_TEMPLATE.md` §3.3（生理单元卡片）
- `docs/model-evaluation/PHYSIO_V2_EVAL_REPORT.md`（顶部口径警示）
- `docs/model-evaluation/NHANES_TRANSPORT_STRESS.md`（ROUND_47 压力测试结果与解释边界）
- `docs/model-evaluation/REAL_ACTIGRAPHY_BASELINE.md`（ROUND_48 同队列真实 actigraphy 基线）
- `docs/model-evaluation/REAL_BASELINE_ROBUSTNESS.md`（ROUND_49 规范曲线与佩戴混杂审计）
- `docs/model-evaluation/REAL_BASELINE_PROTOCOL_ROBUSTNESS.md`（ROUND_50 多日聚合 9 规范审计）
- `docs/thesis/CLAIMS_LEDGER.md`（C-01~C-09 的引用边界）
- `backend/models/artifacts/physiological_optimized/README.md`

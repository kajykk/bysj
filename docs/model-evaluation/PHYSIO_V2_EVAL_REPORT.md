# physiological_optimized · 可复跑评估报告

> **样本量先说：n = 157（单一切分、单一随机种子）。**
> 这个量级下 95% CI 的宽度是**结构性**的，不能据此主张高精度；
> 所有区间只能读作「该量级下点估计的波动范围」。

- 评估对象：`backend/models/artifacts/physiological_optimized/`（registry 中以 L1 主模型启用，见 `model_registry.py:142`）
- 数据集：**`datasets/physiological/external/depresjon_processed/depresjon_physiological.csv`（当前版本，1029 行）**
  的确定性切分 test 集（`stratified_split`, 0.7/0.15/0.15, `random_state=42`）
- 推理链：**生产路径**（`DataCleaner.transform` → `engineer_features` → `SimpleStandardScaler.transform` → MLP），
  与 `predict.py::_predict_physiological_sync` 同一套工件
- 判定阈值：`y_score >= 0.5`
- 复跑命令：

```bash
cd backend
.venv/Scripts/python.exe scripts/modeling/eval/v1_29/01_reproducible_eval.py
# 只复算（不重建预测、不推理）：加 --report-only —— 会重写 JSON + 本报告，
# 且与全量运行的产物**逐字节一致**（ROUND_27 起 csv 存 float64 往返精度、
# 指标与 CI 按 csv 的行序计算）
```

## 一、与原记录的关系（不可复现，不冒充）

`metrics.json` 记录的测试集是 **n=139（TP=41 / FP=3 / FN=11 / TN=84）**，
本报告**没有**复现它，也不会用它替代它。实测证据（`--verify-original`；以下证据全部取自
**修复前** artifact，已存档为 `*.broken_round29`，ROUND_29 更换——它们解释的是
**旧 139 行测试集为何不可复现**，与当前生产链无关）：

| 检查项 | 实测 | 记录值 | 结论 |
|---|---|---|---|
| 切分输出（`stratified_split`, rs=42, 1029 行 359 阳性/670 阴性） | 719 / 153 / 157 | 719 / 171 / 139 | **不一致**；该函数两个历史版本逐行相同，输出恒定 |
| 修复前 `scaler.json`（存档）的 sleep_quality 均值 | 5.4279 | 5.4279 | 仓内三份数据（depresjon 2.84 / augmented 2.83 / kaggle Mood_Rating≈5.07）**都对不上**，且 5.43 超出 1-5 量表 |
| 修复前 artifact scaler 变换当前数据后的 z 分数 | 多列 abs(mean_z) > 1（sleep_quality -1.00、steps -1.41） | 应 ≈ 0 | **训练数据与当前数据不同版本** |

⇒ 原 139 行测试集**不可复现**：训练脚本从未入库，修复前 artifact 的 scaler 统计量指向
一份不在仓内的数据版本。本报告的数字属于**当前仓内数据版本**（ROUND_29 重训后的
co-consistent 工件），与旧记录**不可比**，任何对外材料不得混用两者。

## 二、指标（生产路径，n = 157）

| 指标 | 点估计 | 95% CI（bootstrap, B=10000, seed=42） |
|---|---|---|
| Accuracy | 0.8662 | [0.8089, 0.9172] |
| Precision | 0.7742 | [0.6667, 0.8750] |
| Recall | 0.8727 | [0.7800, 0.9531] |
| F1 | 0.8205 | [0.7387, 0.8889] |
| ROC AUC | 0.9451 | [0.9064, 0.9768] |

混淆矩阵：TP=48 / FP=14 / FN=7 / TN=88

> **Recall 0.8727 是这份报告最需要被读到的数字**：在阈值 0.5 下，
> 每 10 个真实阳性会漏掉约 1 个。该读数是 ROUND_29
> 修复 D-R26-1（生产 scaler 与模型不配套）**之后**的生产链路实测；修复前在同一测试集上
> 为 0.6000（历史口径，不可比）。修复记录与「这是修标准化缺陷、不是模型变强」的论证见 §三。

## 三、D-R26-1 缺陷披露与 ROUND_29 修复记录（修标准化缺陷，不是模型变强）

**缺陷（修复前，存档口径）**：生产 artifact 的 `scaler.json` 与模型权重、训练数据三者
不同源（§一 第 2、3 行的证据取自修复前工件）。在**同一个** n = 157 测试集上，
修复前生产路径 Recall 仅 0.6000（TP=33 / FP=0 / FN=22 / TN=102，历史口径，不可比）；
只把标准化参数换成「当前训练集重拟合」时 Recall 0.9455 / F1 0.9369 / AUC 0.9841
（旧权重下的诊断读数，仅用于定位缺陷，不得宣称为性能）。

**修复（ROUND_29 · 路径 B 端到端重训）**：
`scripts/modeling/eval/v1_29/04_round29_retrain_physiological.py`——cleaner/scaler 只在
train 719 行上拟合，模型经该 scaler 训练（co-consistent by construction）；超参数沿用
`metrics.json` 记录值（不为迁就测试集调参）；固定 seed 42，同 seed 两跑产物逐字节一致；
修复前工件存档为 `*.broken_round29`，原子替换后生产路径复载校验 max|diff| = 0。
永久防复发闸门：`tests/test_p2_56_round29_scaler_consistency.py`（第一层可复现性：
部署 scaler == train-only 重拟合，实测 max|diff| = 0.000e+00；第二层域合理性；结构层）。

**修复后（本报告主口径，同一测试集、同一阈值 0.5）**：
Recall 0.8727（TP=48 / FP=14 / FN=7 /
TN=88）、F1 0.8205、ROC AUC 0.9451。

| 链路 | F1 | Recall | ROC AUC |
|---|---|---|---|
| 生产路径（部署 artifact，co-consistent by construction） | 0.8205 | 0.8727 | 0.9451 |
| 诊断对照（train-only 独立重拟合；ROUND_29 后与生产逐位相等） | 0.8205 | 0.8727 | 0.9451 |

**为什么这是修缺陷、不是模型变强**：修复后 ROC AUC 由修复前的 0.9884 **下降**到
0.9451——修复没有提高任何能力读数，它只是把生产链路换回与训练一致的
标准化，使阈值 0.5 重新有意义；修复前的高 AUC 是错配标准化下的读数，与修复后
不可比。另需如实记账：修复后单切分 Recall 0.8727 **低于**修复前旧权重的
诊断读数 0.9455——本文不追这个数（在测试集上调参即泄漏，见台账 B-05）；新管线的重复
CV（5 折 × 3 次，与 provenance 诊断同折）Recall 为 0.88 ± 0.04，与单切分点估计同量级
（逐折明细见 `docs/P2_56_ROUND29_SCALER_FIX_AUDIT.md`）。

**一致性证明（csv 逐样本列）**：`y_score_refit_scaler`（train-only 独立重拟合过**同一套
生产权重**）与 `y_score` 逐位相等——两列相等即「部署 scaler 就是训练时那一个」的工件级
证据；参数级判据见 p2_56 闸门第一层。修复前那组 0.60 / 0.9455 只在此段作为变更记录出现，
**不得**作为任何性能主张引用。

## 四、可核验性（外部审稿人唯一需要的东西）

逐样本预测已落盘：

```
backend/models/artifacts/physiological_optimized/test_predictions.csv
  sha256 = 1853a250717e0681d5f01c06d6e9278e4449185deaf445aa4f83f025ad55cc94
backend/models/artifacts/physiological_optimized/test_predictions.csv.sha256
```

列定义：`sample_id, row_index, y_true, y_score, y_pred, y_score_refit_scaler`。
`y_score` 是生产链输出；`y_score_refit_scaler` 是 §三 的一致性证明列——ROUND_29 起部署
scaler 与 train-only 重拟合逐位相等，故该列与 `y_score` **逐位相等**；一旦不相等即
D-R26-1 复发（参数级判据见 `tests/test_p2_56_round29_scaler_consistency.py` 第一层）。

复算全部数字（会重写 JSON + 本报告并重算 CI）：

```bash
cd backend
.venv/Scripts/python.exe scripts/modeling/eval/v1_29/01_reproducible_eval.py --report-only
```

**验收口径**：对已提交的 `test_predictions.csv` 跑上面这条命令，重写出的 JSON 与本报告
必须与仓库里的提交版**逐字节相等**（sha256 相同）。这不是「跑两次自洽」——
比的是「提交产物 vs 单命令产物」。

环境指纹（同机器两次运行产物字节一致；换机器需比对以下版本）：

```json
{
  "python": "3.12.0",
  "platform": "Windows-11-10.0.26200-SP0",
  "numpy": "2.4.4",
  "pandas": "3.0.2",
  "scikit_learn": "1.8.0"
}
```

## 五、方法学口径（与旧 json 的统一说明）

- **point 估计 = 全样本统计量**（如 F1 = 2TP/(2TP+FP+FN)），**不是** bootstrap 均值。
  旧 `physio_v2_test_ci.json` 的 `f1.point = 0.8527` 是**bootstrap 均值被误写入 point 位**；
  同一混淆矩阵的名义值是 `0.8541667`（= `metrics.json`），两者差 0.0015 即来源于此。
- **区间 = 非参数 bootstrap 分位**（B=10000, seed=42），AUC 同样用 bootstrap——
  旧 json 的 AUC 解析近似已被取代（旧文件保留为历史记录，顶部已标注；取代关系见 `README.md` §1）。
- 小样本（n=157）下 bootstrap 分位区间可能触到 1.0（precision 上界），属正常现象。

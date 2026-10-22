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
本报告**没有**复现它，也不会用它替代它。实测证据（`--verify-original`）：

| 检查项 | 实测 | 记录值 | 结论 |
|---|---|---|---|
| 切分输出（`stratified_split`, rs=42, 1029 行 670/359） | 719 / 153 / 157 | 719 / 171 / 139 | **不一致**；该函数两个历史版本逐行相同，输出恒定 |
| `scaler.json` 的 sleep_quality 均值 | — | 5.4279 | 仓内三份数据（depresjon 2.83 / augmented 2.83 / kaggle Mood_Rating≈5.07）**都对不上**，且 5.43 超出 1-5 量表 |
| artifact scaler 变换当前数据后的 z 分数 | 多列 abs(mean_z) > 1（sleep_quality -1.00、steps -1.41） | 应 ≈ 0 | **训练数据与当前数据不同版本** |

⇒ 原 139 行测试集**不可复现**：训练脚本从未入库，artifact 的 scaler 统计量指向一份不在仓内的数据版本。
本报告的数字属于**新数据集**（当前 depresjon 版本），与旧记录**不可比**，任何对外材料不得混用两者。

## 二、指标（生产路径，n = 157）

| 指标 | 点估计 | 95% CI（bootstrap, B=10000, seed=42） |
|---|---|---|
| Accuracy | 0.8599 | [0.8025, 0.9108] |
| Precision | 1.0000 | [1.0000, 1.0000] |
| Recall | 0.6000 | [0.4717, 0.7292] |
| F1 | 0.7500 | [0.6410, 0.8434] |
| ROC AUC | 0.9884 | [0.9699, 0.9990] |

混淆矩阵：TP=33 / FP=0 / FN=22 / TN=102

> **Recall 0.6000 是这份报告最需要被读到的数字**：在阈值 0.5 下，
> 每 10 个真实阳性会漏掉约 4 个。原因见 §三。

## 三、生产路径的已知缺陷（scaler 与数据版本不配套）

artifact 的 `scaler.json` 与当前数据分布不匹配（§一 第 2、3 行），而生产推理**正是**用它做标准化
⇒ 概率整体偏低 ⇒ 阈值 0.5 下 recall 被压低。诊断对照（同一 test 集，仅替换 scaler 为「在当前训练集上重拟合」）：

| 口径 | F1 | ROC AUC | Recall |
|---|---|---|---|
| 生产路径（artifact scaler，本报告主口径） | 0.7500 | 0.9884 | 0.6000 |
| 诊断对照（重拟合 scaler，**非生产**） | 0.9369 | 0.9841 | 0.9455 |

AUC 在两个口径下都高 ⇒ **模型的排序能力没问题，问题在标准化参数**。
这是一条需要单独整改的生产缺陷（见 `docs/P2_53_ROUND26_EVAL_REPRODUCIBILITY_AUDIT.md` §T4），
本轮**不**重训、**不**改 artifact。

## 四、可核验性（外部审稿人唯一需要的东西）

逐样本预测已落盘：

```
backend/models/artifacts/physiological_optimized/test_predictions.csv
  sha256 = 42824d46dc5ae344790e447a346c61aad8bb23ca1317f1ee6b9cd8aca6d22055
backend/models/artifacts/physiological_optimized/test_predictions.csv.sha256
```

列定义：`sample_id, row_index, y_true, y_score, y_pred, y_score_refit_scaler`。
`y_score` 是生产链输出；`y_score_refit_scaler` 是 §三 的诊断列（**不入主口径**）。

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

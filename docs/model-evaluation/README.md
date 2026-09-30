# 模型评估证据（论文/答辩用图与数据）

生成方式均为仓库真实数据 + 真实产物实测，可复现（见各节命令）。

## 1. 生理 MLP v2 测试集不确定性

- `physio_v2_test_ci.json`：测试集 n=139 的 95% CI。
  阈值指标（Acc/Prec/Rec/F1）为非参数 bootstrap（B=10000，seed=42），
  混淆对由 `backend/models/artifacts/physiological_optimized/metrics.json`
  反推（TP=41, FP=3, FN=11, TN=84，已用 acc/prec/rec 交叉验证）；
  AUC 因未持久化逐样本分数，采用 Hanley-McNeil SE（保守近似，已标注方法）。
- `physio_v2_test_ci.png`：论文第 4 章直接引用。关键口径：
  F1=0.854 [0.769, 0.923]，Recall=0.788 [0.672, 0.896] ——
  区间宽是 n=139 的必然结果，答辩时主动说明，不宣称高精度。

## 2. 融合权重敏感性

- `fusion_weight_sensitivity.csv/.png`：结构化权重 0.35–0.75 扫描
  （文本/生理按 0.30/0.15 比例缩放，关闭置信度加权以隔离权重效应）。
- 结论：模态一致时 spread≈1.6（鲁棒）；模态冲突时 spread=19.3，
  即**权重只在模态打架时重要** —— 这正是保留人工复核与危机词优先规则的依据。

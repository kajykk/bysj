# 模型注册表与世系 (MODEL REGISTRY) — SSOT 配套文档

> 版本口径 SSOT：`backend/app/core/config.py`（`RELEASE_CODENAME` / `Settings.app_version = 3.1.0`）。
> 本文件是模型口径的唯一事实表：**生产用哪个模型、论文用哪个、其余是什么**，答辩/运维一律以此表为准。
> 各模型 `metrics.json` 路径附后，均可复核。

## 1. 生产模型（线上推理唯一默认）

| 槽位 | 模型 | 版本开关 | 关键指标 | 产物位置 |
|---|---|---|---|---|
| 结构化 | LogisticRegression（Mendeley PHQ-9 真实数据训练，external Pipeline） | `STRUCTURED_DEFAULT_MODEL=v1.23`（默认；`v1.20` 为回滚位） | F1=0.8955 / AUC=0.9174 / Acc=0.8811（达标：F1≥0.85、AUC≥0.90） | `backend/models/`（`MODEL_DIR`） |
| 熔断兜底 | 规则回退（与模型版本无关） | `STRUCTURED_MODEL_MODE=fallback` | — | 代码内规则引擎 |

特征契约：12 个小写原始列，缺失兜底见 `feature_maps.DEFAULTS`（训练集中位数）。

## 2. 论文模型（离线实验结论，不直接 serving）

| 用途 | 模型 | 指标 | 备注 |
|---|---|---|---|
| 论文最终选型 | CatBoost（阈值 0.40） | F1=0.8708 / AUC=0.9177 / Acc=0.9240 | 论文第 4 章实验结论；生产仍用 LR v1.23（F1 更高），差异已在论文“选型 vs 投产”段落说明 |

## 3. 实验基线（非生产，仅对比/消融）

| 模型 | 指标 | 状态 |
|---|---|---|
| 结构化 GBDT m1 | F1=0.8608 / AUC=0.9140 | 低于 LR 基线，**未投产**（诚实记录） |
| 文本 TF-IDF+LR（232 维稠密） | F1=0.789 / AUC=0.881（n=26,381） | 基线 |
| 生理 MLP（input_dim=13，NumPy + PyTorch 双实现） | F1=0.857 / AUC=0.958 | 基线 |
| 融合 m4 stacking（n=1,275） | 多模态加权融合 + 优先级规则引擎 | 实验 |
| BERT ONNX（fp32 388MB / int8 97.75MB） | CPU 优化两档 | 实验/影子对拍 |

## 4. 历史/重复产物（deprecated，不得作为生产引用）

| 路径 | 定性 |
|---|---|
| `artifacts_v1.3_baseline` | 历史基线快照，仅归档 |
| `model_assessment/`、`structured_run/`、`best_model.pkl`（238MB） | 实验中间产物，已被上表模型取代；清理前保留只读，禁止新代码引用 |

## 5. 治理链路（真实代码，非文档模型）

多模态加权融合与缺失模态权重重分配、危机词优先规则、KS/PSI 漂移检测、
金丝雀流量分配与自动回滚、NumPy SMOTE、McNemar/Bonferroni 统计检验、
SHAP 近似可解释、实验管理服务群。运行期 `/health` 中 `models: ok` 即全部产物加载成功。

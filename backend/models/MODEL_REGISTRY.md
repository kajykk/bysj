# 模型注册表与世系 (MODEL REGISTRY) — SSOT 配套文档

> 版本口径 SSOT：`backend/app/core/config.py`（`RELEASE_CODENAME` / `Settings.app_version = 3.1.0`）。
> 本文件是模型口径的唯一事实表：**生产用哪个模型、论文用哪个、其余是什么**，答辩/运维一律以此表为准。
> 各模型 `metrics.json` 路径附后，均可复核。

## 0. 2026-11 交付口径（D5 / D6）

- **D5 制品分发**：模型权重与训练/测试数据**不随代码仓库或镜像分发**。生产从外部制品库
  （GitHub Release / 对象存储）获取，下载后按清单 `.sha256` 校验，并以只读卷挂载到 `MODEL_DIR`。
  生产环境缺失任一必需制品、清单哈希不一致、清单缺失/非法、或 `MODEL_BERT_REVISION`
  非 40 位 commit hash 时**启动失败**；开发/测试环境允许降级，但 `/health` 的
  `deployment.model_artifacts` 显示 `degraded`，并输出 `missing` / `hash_mismatch` /
  `unverified` / `manifest` 字段，同时写警告日志。
  - **必需制品清单（6 项）**在代码内单一维护：`app/core/model_registry.py::DEPLOYMENT_REQUIRED_ARTIFACTS`
    （v1.23 结构化 Pipeline、生理 v2 模型+scaler、双语文本模型+TF-IDF、mmp sy lite）。
  - **完整性清单**：`backend/models/DEPLOYMENT_MANIFEST.json`
    （schema `dws-deployment-artifacts/v1`，逐条含 `model_id` / `path` / `bytes` / `sha256`）。
    获取方式：
    1) 从制品库下载 6 个产物到 `MODEL_DIR`（本地即 `backend/models/`）；
    2) 同目录放置 `DEPLOYMENT_MANIFEST.json` 与各制品同名 `.sha256`；
    3) 重新生成（训练侧）：`cd backend && .venv/Scripts/python.exe scripts/artifact_manifest.py`。
    分发路径：制品库 → 部署机 `MODEL_DIR`（只读卷）→ 启动期校验；清单与制品必须同一批次。
    **版本控制口径**：清单 `DEPLOYMENT_MANIFEST.json` 与各 `.sha256` 侧车（仅含哈希、不含模型本体）
    作为审计材料**随仓库入库**；制品本体（`*.pkl` / `*.csv` 等）不入库，二者必须同批次发布，
    仓库只追溯“发布的是哪一批哈希”，不保存权重。
  - 镜像构建上下文只带本文件（`models/MODEL_REGISTRY.md`），不打包 `*.pkl` / `*.csv`；
    归档目录 `models/_archive/` 永不进镜像。
- **D6 融合 DNN**：`fusion_dnn_best` / `fusion_cross_modal_best` / `fusion_transformer_best`
  **不纳入交付**。生产口径固定为 **“多模态加权融合 + 优先级规则兜底”**；DNN 仅作为论文
  实验项，不参与 serving，也不得在答辩材料中表述为线上能力。
- **退役条目（retired）**：注册表中指向不存在文件的 8 个条目（上列三个 DNN、
  `physiological_risk_model`、`physiological_risk_scaler`、`structured_random_forest_quick`、
  `structured_best_ensemble_quick`、`structured_best_threshold`）统一标记
  `lifecycle="retired"` + `enabled=False` + `resolvable=False`；信息不删除，仅保留用于历史对比。
- **非文件条目**：`structured_v1.23_external_scaler` 标记 `resolvable=False` ——
  **v1.23 的 scaler 已内嵌在 `model.pkl` 的 sklearn Pipeline 内，无独立 `scaler.pkl` 文件**，
  不应单独加载。
- **测试专用产物**：`backend/models/v1.23_external_lr/preprocessor.pkl` 仅供离线脚本/测试
  （`test_only`），运行期不加载；已由 `backend/.dockerignore` 的 `*.pkl` 规则排除在镜像外。

### 0.1 使用边界（交付声明）

- `automated_decision_allowed = false`：所有模型输出仅为**辅助提示/风险分层**，
  不得用于自动诊断、自动分诊、自动拒保或任何无需人工复核的处置决策。
- **人群范围**：仅登记学生/青年自报问卷人群（Kaggle Student Depression + Mendeley PHQ-9）；
  非学生成人、临床患者、未成年人、孕产妇及非英语人群**均未验证**，不得跨人群直接使用。
- **目标域校准标签数 = 0**：当前没有目标部署域的标注数据，概率阈值未做目标域校准；
  跨机构/跨语种部署前必须重新收集标注并做阈值与校准回归（ECE/Brier 复核）。

## 1. 生产模型（线上推理唯一默认）

| 槽位 | 模型 | 版本开关 | 关键指标 | 产物位置 |
|---|---|---|---|---|
| 结构化 | LogisticRegression（Kaggle 学生自报 + Mendeley PHQ-9 加权训练，external Pipeline） | `STRUCTURED_DEFAULT_MODEL=v1.23`（默认；`v1.20` 为回滚位） | 内部测试 F1=0.8589 / AUC=0.9131；干净跨来源 AUC=0.8633 / Brier=0.1734 | `backend/models/v1.23_external_lr/`（`MODEL_DIR`） |
| 熔断兜底 | 规则回退（与模型版本无关） | `STRUCTURED_MODEL_MODE=fallback` | — | 代码内规则引擎 |

特征契约：12 个小写原始列，缺失兜底见 `feature_maps.DEFAULTS`（训练集中位数）。

**人群与验证口径**：v1.23 训练母表为 Kaggle Student Depression 27,870 行（自报二分类）
+ Mendeley 682 行（PHQ-9≥10，`sample_weight=5.0x`），标签不是临床诊断。内部测试
n=4,318（阳性率 58.13%，AUC 0.9131 / F1 0.8589）；干净 Kaggle→Mendeley 跨来源
n=682（AUC 0.8633 / Brier 0.1734 / ECE 0.1435），0.5 阈值只报出约一半阳性。
**当前只登记学生/青年自报问卷人群**；非学生成人、临床人群、非英语人群均未验证，
运行时以 `population_scope` 披露，详见 `docs/model-evaluation/POPULATION_EVIDENCE_MATRIX.md`。

## 2. 论文模型（离线实验结论，不直接 serving）

| 用途 | 模型 | 指标 | 备注 |
|---|---|---|---|
| 论文最终选型 | CatBoost（阈值 0.40） | F1=0.8708 / AUC=0.9177 / Acc=0.9240 | 论文第 4 章实验结论；生产仍用 LR v1.23（F1 更高），差异已在论文“选型 vs 投产”段落说明 |

## 3. 实验基线（非生产，仅对比/消融）

| 模型 | 指标 | 状态 |
|---|---|---|
| 结构化 GBDT m1 | F1=0.8608 / AUC=0.9140 | 低于 LR 基线，**未投产**（诚实记录） |
| 文本 TF-IDF+LR（232 维稠密） | F1=0.789 / AUC=0.881（n=26,381） | 基线 |
| 生理 MLP（input_dim=13，NumPy + PyTorch 双实现） | F1=0.857 / AUC=0.958 | 基线；**合成特征管线，指标不得作真实生理性能引用**（见下方注） |
| 融合 m4 stacking（n=1,275） | 多模态加权融合 + 优先级规则引擎 | 实验；生产口径即为“加权融合 + 规则兜底” |
| 融合 DNN（dnn / cross_modal / transformer `.keras`） | 未纳入交付（D6，`resolvable=False`） | 论文实验项；不得作为线上能力表述 |
| BERT ONNX（fp32 388MB / int8 97.75MB） | CPU 优化两档 | 实验/影子对拍；**2026-10-04 定性：注册条目与 `models/text/bert_text_classifier/` 权重已归档**（见 §6） |

> **生理 MLP 指标注（2026-11-02 来源审计）**：`depresjon_physiological.csv` 的
> `heart_rate`/`sleep_hours`/`sleep_quality`/`systolic_bp`/`diastolic_bp` 由真实队列标签
> 的分组均值生成，`phq9_score` 也是标签的噪声副本；仅 `steps`/`exercise_minutes`
> 来自真实 actigraphy。仅真实列 5 折 OOF AUC 为 0.6443，合成列可达 0.9898。
> 因此 F1=0.857 / AUC=0.958 / AUC 0.9451 等读数只能作管线一致性/回归读数，
> **不得**作为真实生理信号性能引用。详见 `docs/model-evaluation/PHYSIO_DATA_PROVENANCE_AUDIT.md`。

## 4. 历史/重复产物（deprecated，不得作为生产引用）

| 路径 | 定性 |
|---|---|
| `artifacts_v1.3_baseline` | 历史基线快照，仅归档 |
| `model_assessment/`、`structured_run/`、`best_model.pkl`（238MB） | 实验中间产物，已被上表模型取代；清理前保留只读，禁止新代码引用 |

## 5. 治理链路（真实代码，非文档模型）

多模态加权融合与缺失模态权重重分配、危机词优先规则、KS/PSI 漂移检测、
金丝雀流量分配与自动回滚、NumPy SMOTE、McNemar/Bonferroni 统计检验、
SHAP 近似可解释、实验管理服务群。运行期 `/health` 中 `models: ok` 即全部产物加载成功；
`deployment.model_artifacts: degraded` 表示开发/测试环境缺少生产必需制品（生产环境会直接启动失败）。

## 6. 2026-10-04 决策：模型镜像**不新增** transformers（**不卸载**）

> ⚠️ 2026-10-04 复核修正：本节初版曾断言「`requirements.txt`/`requirements.lock` 均无
> transformers」——**该断言错误且未经验证**。实测：`requirements.txt:34` 已声明
> `transformers>=5.3.0`，且被生产代码真实 import（见下表）。决策已按事实重写。

| 项 | 事实（2026-10-04 实测） |
|---|---|
| 依赖现状 | `requirements.txt:34` 已声明 `transformers>=5.3.0`（非新增，非本轮引入） |
| 生产代码 import 面 | `app/services/experiment_trainer.py:43`、`app/services/experiment_evaluator.py:72`（用户实验页的训练/评估）、`app/core/model_engine/loading.py:409/461/467/473`（BERT 加载分支）、`app/core/text_m2_bert_predictor.py:62` |
| 降级机制 | `app/core/config.py:42-75` 有 `TRANSFORMERS_AVAILABLE`（`importlib.util.find_spec` 探测）+ 各调用点惰性 import → 缺包时优雅降级，不硬崩 |
| **决策** | **不新增**（维持现状，零新增依赖）**、不卸载** |
| 不卸载的理由 | ①卸载会直接破坏用户实验页的 BERT 训练/评估功能（`ExperimentTab.vue:337/354` 显式传 `text_bert_classifier`，走 `experiment_trainer/evaluator`）；②代码已做优雅降级，保留的运行成本可控；③移除能否显著缩小镜像**未实测**（PyPI 不可达，无法构建镜像对比）——不做无证据的优化 |

**衍生后果（须知晓）**：BERT 权重已于同日归档（§3、§4），因此实验页的 BERT 训练即使跑通，
产物落在 `models/text/bert_text_classifier/` 也**无法被加载**——`text_bert_classifier` 注册条目
已从 `MODEL_PATHS` 移除，`model_engine/loading.py:311` 会以「未注册」拒绝。若要恢复 BERT
训练能力，需**同时**恢复注册条目 + 产物目录（或改走 P2-1 句向量路线）。是否禁用实验页的
BERT 入口属产品决策，未擅自改动。

**真实复核口径**（预期为「有命中」，用于确认依赖仍被使用）：
```bash
grep -rn "transformers" backend/requirements.txt backend/requirements.lock   # 应有命中（依赖声明）
grep -rn "^\s*\(import transformers\|from transformers\)" backend/app        # 应有命中（实验与 BERT 加载路径）
```

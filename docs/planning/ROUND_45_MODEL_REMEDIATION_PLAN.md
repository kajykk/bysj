# ROUND_45 结构化 / 生理模型整改计划

- 日期：2026-11-01
- 基线 HEAD：`c8622f7`
- 触发证据：`outputs/probe_other_models_2026-11-01.json`、`outputs/probe_other_models_extra_2026-11-01.json`
- 约束：不提交、不删除测试危机事件、不擅自替换生产模型工件；模型工件改动需留快照与前后读数。

## 0. 范围与非目标

**范围**

1. 结构化 v1.23 推理契约：GPA 量纲、路由模型 ID、置信度展示、阈值口径文档。
2. 生理 v2 推理契约：降级标记真实性、空/非法输入、启发式睡眠质量量纲、注册表元数据。
3. 以离线候选实验评估「特征去重」与「派生特征重构」是否值得进入下一轮模型升级。

**非目标**

- 不在本轮静默更换生产模型工件（`models/v1.23_external_lr/`、`models/artifacts/physiological_optimized/`）。
- 不改数据库 schema、不改已有用户评估记录。
- 不提交 git；不触碰工作区中既有的文本模型改动。

## 1. 根因与处置

| ID | 问题 | 证据位置 | 处置 | 级别 |
|---|---|---|---|---|
| S-1 | 训练集 `cgpa ∈ [0,4]`，UI 滑杆 0–10；小写 `cgpa` 原样进入模型 | `backend/app/core/model_engine/inference.py:416-419,473-478`；`frontend/src/views/user/components/structured-steps/AcademicStep.vue:8-11` | 小写 `cgpa` 统一归一到 0–4；大写 `CGPA` 保持 0–10 供 v1.20/实验路径 | P0 |
| S-2 | `routing_info.selected_model_id` 恒为 v1.20，`model_used` 实为 v1.23 | `inference.py:526`；`predict.py:262-280` | 路由 ID 跟随 `structured_default_model`；主路径结束后以实际 `model_used` 覆写 | P0 |
| S-3 | 前端只显示覆盖度置信带，不显示实际 `confidence` | `StructuredResultPanel.vue:49-55,78,130` | 新增实际置信度展示；文案区分「覆盖度」与「模型置信度」 | P1 |
| S-4 | 生产分级阈值 25/45/65/85 与工件 `18/35/55/72` 双口径，文档却称工件为生产源 | `backend/app/core/risk_thresholds.py:15-37`；`backend/app/core/ml_decision_thresholds.py:26` | 本轮不改变分级行为；把文档口径改为「运行时为生产唯一源，工件仅供评估」，并加一致性断言 | P1 |
| P-1 | 普通异常路径静默返回启发式，响应仍标 DL + `calibrated=True` | `backend/app/core/model_engine/predict.py:1011-1046` | `_predict_physiological` 返回 `(score, fallback_reason)`；上层如实置 `fallback_used/model_used/calibrated` | P0 |
| P-2 | 空字典/全未知字段可推理并落库，默认人取得 42.64 分 | `backend/app/schemas/model_predict.py:93-130`；`backend/app/core/model_engine/predict.py:1048-1090` | schema 要求至少一个可识别且有限数值字段；`None`/NaN/Inf 显式 422 | P0 |
| P-3 | 启发式 `sleep_quality` 按 0–10 计，UI/模型按 1–5；质量 5 被算成中等风险 | `backend/app/core/model_engine/fallback.py:251-266` | 启发式改用 1–5 量纲；补回归测试 | P0 |
| P-4 | 注册表元数据仍写 [64,32,16]/dropout 0.3/F1 0.9530/3745 参数 | `backend/app/core/model_registry.py:140-166` | 对齐 `metrics.json` 实际值，并标注评估集 n=157 单切分 | P1 |
| M-1 | 派生特征 `activity_intensity=steps/exercise` 在运动分钟极小时爆炸；睡眠/运动响应非单调 | `backend/app/ml/feature_engineering.py:45-110`；probe 读数 | 离线候选重训评估；生产工件不换 | P2 |

## 2. Phase 0：基线与快照

1. 复制 `backend/models/v1.23_external_lr/` → `outputs/model_snapshots/2026-11-01/v1.23_external_lr/`。
2. 复制 `backend/models/artifacts/physiological_optimized/` → `outputs/model_snapshots/2026-11-01/physiological_optimized/`。
3. 固化基线读数：两份 probe JSON（已存在，`outputs/probe_other_models*_2026-11-01.json`）。
4. 若后续进入候选重训，候选产物只写入 `outputs/candidates/`，不覆盖生产目录。

**验收**：快照目录文件数与源目录一致；sha256 抽样一致。

## 3. Phase 1：代码修复（本轮执行）

### 3.1 结构化 GPA 归一（S-1）

- `_build_structured_input` 中：
  - `gpa_scale` 显式优先；否则 `cgpa <= 4 → 4`，`cgpa > 4 → 10`。
  - `cgpa_0_4 = cgpa / gpa_scale * 4`，仅当 raw 提供 `cgpa` 时覆写小写特征。
  - 大写 `CGPA = cgpa_0_4 / 4 * 10`，保持既有 0–10 派生契约。
- 新增测试：`cgpa=8.5`（10 分制）进入 v1.23 → `cgpa≈3.4`；`cgpa=3.5` 透传；缺省仍用 `DEFAULTS`。

### 3.2 路由模型 ID 与置信度（S-2、S-3）

- `_route_structured` 按 `settings.structured_default_model` 写 `selected_model_id`。
- `predict_structured` 主路径结束后将 `routing_info.selected_model_id` 覆写为实际 `model_used`。
- 前端结果面板新增「模型置信度」行（`confidence` 百分比），把现有 band 标签改为「特征覆盖置信带」。
- 新增测试：v1.23 主路径 `routing_info.selected_model_id == model_used`；前端单测断言置信度渲染。

### 3.3 生理降级真实性（P-1）

- `_predict_physiological` 返回 `tuple[float, str | None]`：
  - `FileNotFoundError → model_not_found`
  - `ImportError → dependency_not_installed`
  - 其他异常 → `prediction_error`
  - `ModelException` 继续上抛（503）。
- `predict_physiological` 解包；reason 非空时：`fallback_used=True`、`model_used=physiological_heuristic_fallback`、`calibrated=False`、`fallback_reason=reason`，并计入 `_incr_fallback`。
- 非有限分数路径保持原有更高优先级。
- 更新两处调用测试（`test_predict_nonfinite_guards.py`、`test_v128_quality_regressions.py`）。

### 3.4 生理输入边界（P-2）

- `PhysiologicalPredictRequest` 新增：
  - 至少一个可识别字段，否则 422。
  - `None` 显式拒绝；非数值拒绝；NaN/Inf 拒绝（`math.isfinite`）。
- 置信度缺失计数只统计缺失/`None`/非有限，未知键不再抬高质量。
- 新增 API/schema 测试：`{}`、`{"foo":1}`、`{"sleep_hours": None}`、`{"heart_rate": NaN}` → 422；合法单字段 → 200。

### 3.5 启发式睡眠质量量纲（P-3）

- `sleep_quality` clamp `(0,5)`，风险 `(5 - quality) / 4`。
- 新增测试：quality 5 → 该分量 0；quality 1 → 该分量满值。

### 3.6 阈值口径与注册表（S-4、P-4）

- `ml_decision_thresholds.py` 表项改为运行时 `risk_thresholds.MODALITY_RISK_THRESHOLDS` 为唯一生产源，工件 18/35/55/72 仅评估口径。
- `model_registry.py` 元数据对齐 `metrics.json`：
  - hidden `[128,64,32,16]`、dropout `0.2`、params `13153`、best_epoch `27`
  - F1 `0.8205`、acc `0.8662`、AUC `0.9451`、AUPRC `0.8919`
  - 评估集 `n=157`（单切分、单种子）
- 新增测试：注册表元数据 == `metrics.json` 关键字段；文档表不再声称工件阈值是生产源。

## 4. Phase 2：离线候选实验（不换生产工件）

1. **结构化去重候选**：在 `outputs/candidates/` 训练 LR 候选，特征去除 `academic_pressure` 或 `anxiety`（二选一/复合），固定同一 train/val/test，对比 AUC/F1/校准。
2. **生理派生特征候选**：
   - 方案 A：仅 7 原始特征 + `bp_category`。
   - 方案 B：保留派生但修正 `activity_intensity = steps / max(exercise_minutes, 30)` 并对派生值按训练分位数截断。
   - 固定同一 719/153/157 切分与超参，报告 test F1/AUC/AUPRC + 运动/睡眠单调性探针。
3. **门禁**：候选指标不劣于现工件（F1/AUC 容差 -0.02）且探针非单调性消失，才提交「是否升级」决策；否则保留现工件并在报告中说明。

## 5. Phase 3：验证矩阵

- 后端定向：`test_d1_feature_contract.py`、`test_feature_maps.py`、`test_s02_structured_v123_default.py`、`test_regression_v128_quality.py`、`test_model_engine.py`、`test_predict_nonfinite_guards.py`、`test_v128_quality_regressions.py`、`test_predict_physiological_*`、`test_schema_v116.py`、`test_model_registry.py`。
- 后端全量：`backend/.venv/Scripts/python.exe -m pytest -q`（若时间允许）。
- 前端：`npm run test -- --run`（或项目脚本）+ `npm run build`。
- 行为回归：重跑两份 probe，记录修复前后 `risk_score/risk_level/model_used/fallback_used` 差异表。
- 证据落盘：`outputs/probe_other_models_after_2026-11-01.json`、`outputs/ROUND_45_REMEDIATION_EVIDENCE.md`。

## 6. 回滚

- 代码回滚：按文件 `git checkout -- <file>`（仅限本轮改动文件，执行前先确认无用户未提交内容）。
- 工件回滚：从 `outputs/model_snapshots/2026-11-01/` 复制回生产目录，并校验 `.sha256`。
- 本轮不提交、不推送，回滚面仅限工作区。

## 7. 决策记录

- D1：GPA 以训练分布 0–4 为模型输入契约，10 分制输入在推理边界归一。
- D2：降级必须如实上报，宁可 UI 显示「启发式」，不谎报 DL + 已校准。
- D3：空输入在 API 边界 422，不生成「默认人」风险分，不落库。
- D4：阈值分级行为本轮不变，先消除文档/口径冲突；是否切换到工件阈值需独立评估。
- D5：模型工件升级不自动执行；候选实验通过门禁后再决策。

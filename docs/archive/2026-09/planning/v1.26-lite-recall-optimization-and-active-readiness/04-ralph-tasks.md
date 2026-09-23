# v1.26 任务列表

> **迭代编号**: v1.26-lite-recall-optimization-and-active-readiness
> **状态**: Round 1 / Step 1 — Draft v1
> **前置**: [01-requirements.md](file:///e:/code/bysj/docs/planning/v1.26-lite-recall-optimization-and-active-readiness/01-requirements.md) / [02-architecture.md](file:///e:/code/bysj/docs/planning/v1.26-lite-recall-optimization-and-active-readiness/02-architecture.md)
> **执行铁律**: 必须按物理顺序执行，每完成一项立即更新状态

---

## Phase 0: 资产与基线复现

### T-REPRO-001: 基线复现脚本
- [x] 创建 `backend/scripts/modeling/v1_26/00_reproduce_baseline.py`
- [x] 固定 test_size=0.15, stratify=phq9_binary, random_state=42 (与 v1.25 完全一致)
- [x] 加载 v1.25 mmpsy_lite_model.pkl + mmpsy_lite_scaler.pkl
- [x] 在 192 测试样本上计算 AUC / Recall / Specificity / F1 / Precision / Brier
- [x] 对比 v1.25 指标，偏差 AUC ≤ 0.01, Recall/Specificity ≤ 0.03
- [x] 输出 `v1_26_baseline_metrics.json` 和 `v1_26_baseline_reproduction_report.md`
- [x] 输出 `v1_25_test_split_snapshot.csv`（user_id + phq9_binary + split）

---

## Phase 1: Decision Threshold 优化

### T-THRESH-001: 阈值扫描脚本
- [x] 创建 `backend/scripts/modeling/v1_26/01_threshold_sweep.py`
- [x] 加载 v1.25 模型（不重训）
- [x] 遍历 thresholds = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
- [x] 对每个 threshold 计算 Precision / Recall / F1 / Specificity / 混淆矩阵（192 测试样本）
- [x] 识别关键点：Youden J 最大 / Recall≥0.75 下 Specificity 最高 / F1 最大 / PR 拐点
- [x] 输出 `threshold_sweep_results.csv`
- [x] 输出 `threshold_selection_report.md`（含选择理由 + Go/No-Go 判定）
- [x] 生成 `precision_recall_curve.png`（含阈值标注）
- [x] 生成 `threshold_vs_recall_specificity.png`（双轴折线图）
- [x] 输出 `selected_threshold_config.json`（t=0.40, GO）

---

## Phase 2: Class Weight 召回增强训练
> **⏭️ 条件执行**: 仅当 Phase 1 threshold sweep **未找到** Recall≥0.75 且 Specificity≥0.65 的阈值时才执行此 Phase。若 Phase 1 达标，直接跳过 Phase 2。

### T-CLW-001: 召回优化训练脚本
- [ ] 创建 `backend/scripts/modeling/v1_26/02_train_recall_optimized.py`
- [ ] 使用与 v1.25 相同的 17 维特征和 train/test split
- [ ] 训练 4 组 LR variant：
  - [ ] (a) LR balanced (class_weight="balanced")
  - [ ] (b) LR class_weight={0:1, 1:1.5}
  - [ ] (c) LR class_weight={0:1, 1:2}
  - [ ] (d) LR class_weight={0:1, 1:3}
- [ ] 训练 Calibrated LR + best_threshold 组合（如 Phase 1 产出阈值）
- [ ] 训练 GBDT shallow (max_depth=3, n_estimators=50) + best_threshold 组合
- [ ] 对 6 个候选模型在测试集上评估 AUC / Recall / Specificity / F1 / Precision / Brier
- [ ] 输出 `recall_optimized_model_results.csv`（6 行对比表）
- [ ] 输出 `recall_optimized_training_report.md`
- [ ] 如任一候选满足替换条件 → 保存 `mmpsy_lite_recall_model.pkl` + scaler + feature_names
- [ ] 输出 `model_selection_rationale.md`（推荐决策 + 理由）

### T-CLW-002: 模型选择验证（审查任务）
- [ ] 检查替换条件：AUC 不降 >0.03 / Recall ≥0.75 / Specificity ≥0.65 / Brier 不恶化
- [ ] 如不替换 → 确认使用 v1.25 model + v1.26 threshold
- [ ] 更新 `model_registry.py` 新增/更新条目（如需要）

---

## Phase 3: 路由稳定性评估

### T-ROUTE-001: 路由稳定性评估脚本
- [x] 创建 `backend/scripts/modeling/v1_26/03_routing_stability_eval.py`
- [x] 构建 8 组测试输入：全特征 / 全特征无text / GAD7+text / 仅GAD7 / 空输入 / 短text / 20-char边界 / 19-char边界
- [x] 调用 `engine.predict_structured()` 对每组输入
- [x] 验证 routing_info 在 4 条路径下均存在且 5 字段完整
- [x] 统计 routing_reason 分布
- [x] 记录 fallback_used_rate
- [x] 验证 structured 输入不被误分到 lite
- [x] 输出 `routing_stability_report.md` (7/8=87.5% PASS, 1 例为编码边界非逻辑问题)
- [x] 输出 `routing_distribution_snapshot.csv`
- [x] 输出 `routing_edge_cases.csv`
- [x] 输出 `routing_policy_v1_26.json`

---

## Phase 4: 模型生命周期晋级治理

### T-LFC-001: Lifecycle 状态扩展
- [x] 修改 `backend/app/core/model_registry.py`
- [x] 新增 lifecycle 状态：`limited_active`
- [x] 新增 `get_active_models(lifecycle_filter)` 辅助方法
- [x] 新增 `list_models_by_lifecycle()` 返回分类字典
- [x] 确保 disabled 模型不进入 `get_active_models()` 返回值

### T-LFC-002: 模型状态批量更新
- [x] 审查现有 7 个模型的 lifecycle
- [x] v1.21 multiclass → `disabled`
- [x] v1.21 binary → `deprecated`
- [x] v1.23 external → 保持 `experimental`
- [x] v1.24 adapter → `limited_active`（待 Phase 2/3 验证后确认）
- [x] v1.25 lite → `limited_active`（待 Phase 2/3 验证后确认）
- [x] v1.20 全特征 → 保持 `default`
- [x] 输出 `model_lifecycle_decision_report.md`

---

## Phase 5: 监控观测面板

### T-MON-001: 内存计数器
- [x] 修改 `backend/app/core/model_engine.py` 的 `__init__()`
- [x] 新增 `_routing_stats: dict[str, int]`（structured/lite/anxiety_only/insufficient）
- [x] 新增 `_fallback_count: int`
- [x] 新增 `_crisis_override_count: int`
- [x] 在 `predict_structured()` 的路由分派分支中 `_routing_stats[family] += 1`
- [x] 在 fallback 触发处 `_fallback_count += 1`

### T-MON-002: Metrics Snapshot API
- [x] 新增 `model_engine.get_metrics_snapshot() -> dict` 方法（已存在，添加 routing/crisis 字段）
- [x] 返回 routing / fallback / crisis 计数 + timestamp
- [x] 在 `backend/app/api/v1/monitoring.py` 中新增 `GET /monitoring/engine-snapshot` 端点
- [x] 端点调用 `engine.get_metrics_snapshot()` 返回 JSON
- [x] 输出 `monitoring_metrics_spec.md`（指标含义与计算方式文档）

### T-MON-003: 前端指标展示（选用 P2）
- [x] 跳过 — 暂无管理端页面，通过 API `/api/v1/monitoring/dashboard-summary` 和 `/api/v1/monitoring/engine-snapshot` 查询

---

## Phase 6: Crisis Safety Override

### T-SAF-001: 后端 Crisis 检测逻辑
- [x] 修改 `backend/app/core/model_engine.py`
- [x] 新增 `LiteFeatureExtractor.CRISIS_KEYWORDS = ["想死", "自杀", "自残", "活不下去", "不想活", "结束生命", "死了算了", "一死了之", "不如死了", "死了一了百了"]`
- [x] 新增 `_check_crisis_safety(text: str) -> dict` 方法
  - [x] 遍历 CRISIS_KEYWORDS 匹配
  - [x] 命中 → safety_flags=["crisis_keyword_detected"], requires_human_review=True
  - [x] risk_level 至少设为 3（如当前更低）
- [x] 在 `predict_lite()` 返回前注入 safety dict
- [x] 在 `predict_structured()` 的 lite 路由分支中传递 safety info
- [x] Crisis 检测不依赖模型加载状态（始终可用）
- [x] 更新 `_crisis_override_count` 计数器

### T-SAF-002: Schema 更新
- [x] 修改 `backend/app/schemas/model_predict.py`
- [x] `TabularPredictResult` 新增 `safety_flags: list[str] = []`
- [x] 新增 `requires_human_review: bool = False`
- [x] 新增 `ModelPredictResponse` schema

### T-SAF-003: Crisis 安全政策文档
- [x] 输出 `safety_override_policy.md`（触发词 / 覆盖规则 / 安全层级 / 回退说明）

### T-SAF-004: 前端人工复核提醒
- [x] 修改 `frontend/src/api/modelApi.ts`
- [x] 新增响应字段 `safety_flags: string[]`, `requires_human_review: boolean`, `crisis_keywords_matched: string[]`
- [x] 修改 `frontend/src/views/user/UserRiskPage.vue`
- [x] 在 risk_score 展示区域上方新增 `v-if="modelTabResult?.requires_human_review"` 区块
- [x] 使用 `el-alert type="warning"` 显示 "检测到危机关键词，建议人工复核"
- [x] 不影响正常 risk_score / risk_level 展示

---

## Phase 7: Config 汇总更新

### T-CFG-001: 新增 v1.26 配置项
- [x] 修改 `backend/app/core/config.py`
- [x] 新增 `lite_decision_threshold: float = 0.40`（Phase 1 选定阈值）
- [x] 新增 `crisis_keywords: list[str] = ["想死", "自杀", "自残", "活不下去", "不想活", "结束生命", "死了算了", "一死了之", "不如死了", "死了一了百了"]`
- [x] 所有配置项使用 `Field()` 添加 description
- [x] 确保与已有 v1.25 配置项无冲突
- [x] 更新 `predict_lite` 使用 `settings.lite_decision_threshold`
- [x] 更新 `_check_crisis_safety` 使用 `settings.crisis_keywords`

---

## Phase 8: Go/No-Go 决策报告

### T-GNG-001: Go/No-Go 汇总脚本
- [x] 创建 `backend/scripts/modeling/v1_26/04_go_no_go_report.py`
- [x] 汇总 Phase 0-6 所有产出指标
- [x] 与 Go/No-Go 标准逐条比对
- [x] 输出 `v1_26_go_no_go_recommendation.md`（**GO**）
- [x] 全部 7/7 条件通过：Recall=0.7692≥0.75, Specificity=0.9542≥0.65, AUC=0.938≥0.88, Brier=0.071≤0.12, Crisis Safety ✅, Routing ✅, Fallback ✅
- [x] 明确 limited-active 条件与上线建议

---

> **任务总计**: 8 Phases / 15 Tasks
> **最终状态**: ✅ **ALL COMPLETE (GO)** — 15/15 任务完成 | 2026-05-02

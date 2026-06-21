# v1.25 开发任务列表

> **迭代**: v1.25-mmpsy-lite-risk-model
> **日期**: 2026-05-02 | **基线**: Round 3 Locked
> **前置**: [01-requirements.md](file:///e:/code/bysj/docs/planning/v1.25-mmpsy-lite-risk-model/01-requirements.md), [02-architecture.md](file:///e:/code/bysj/docs/planning/v1.25-mmpsy-lite-risk-model/02-architecture.md), [03-design.md](file:///e:/code/bysj/docs/planning/v1.25-mmpsy-lite-risk-model/03-design.md)
> **执行铁律**: 必须按物理顺序执行，严禁跳跃

---

## Phase 0: 数据审计

### T-AUDIT-001: 创建并运行数据审计脚本
- [x] 创建 `backend/scripts/modeling/v1_25/00_data_audit.py`
- [x] 实现 `verify_mmpsy_scores()` 函数 (9 列, 1275 行, phq9/gad7 范围校验)
- [x] 实现 `verify_structured_features()` 函数 (行数 + _source 列统计)
- [x] 标签一致性检查: `phq9_binary == (phq9_score >= 10).astype(int)`
- [x] 运行脚本: `python 00_data_audit.py`
- [x] 产出 `data_audit_report.md`，所有检查项通过

---

## Phase 1: 文本特征工程

### T-FEAT-001: 实现 lite 特征构建脚本
- [x] 创建 `backend/scripts/modeling/v1_25/01_build_lite_features.py`
- [x] 定义 `KEYWORD_CATEGORIES` 常量 (7 类, self_harm_crisis 含 ×2 加权)
- [x] 实现 `chinese_ratio()` — 中文字符占比
- [x] 实现 `check_text_quality()` — 返回 0/1/2 flag
- [x] 实现 `extract_keywords()` — 返回 {keyword_counts, total_keywords, unique_categories, crisis_weighted}
- [x] 逐行构建 21 列特征向量 (user_id + gad7_score + phq9_score[对照用] + 人口学默认值 + 7 kw_ 列 + 4 质量列)

### T-FEAT-002: 运行特征构建并生成报告
- [x] 运行 `01_build_lite_features.py`
- [x] 产出 `data/processed/lite_features.csv` (1275 × 21, 无 NaN, 1114/1275 含关键词)
- [x] 产出 `lite_feature_report.md` (文本质量分布 + 关键词覆盖率 + 关键词密度统计)
- [x] 验证: total_keywords > 0 的样本占比 = 87.4%

---

## Phase 2: 模型训练

### T-TRAIN-001: 实现 lite 模型训练脚本
- [x] 创建 `backend/scripts/modeling/v1_25/02_train_lite_model.py`
- [x] 定义 `MODEL_FEATURES` 常量 (17 维，不含 phq9_score)
- [x] 定义 `GO_THRESHOLDS` 常量 (AUC≥0.80, Recall≥0.75, Specificity≥0.65, Brier≤0.18)
- [x] 实现: train_test_split(stratify, test_size=0.15, random_state=42) + 记录 idx_test
- [x] 实现: StandardScaler 仅在训练集拟合 → transform 测试集
- [x] 实现: 5-Fold CalibratedClassifierCV(isotonic)
- [x] 实现: 测试集 6 指标 (AUC, F1, Precision, Recall, Specificity, Brier)
- [x] 实现: Pearson r + Spearman ρ (vs phq9_score, 使用 idx_test)

### T-TRAIN-002: 训练主模型 (LR)
- [x] 运行训练脚本，LR 训练完成
- [x] AUC=0.938, F1=0.743, Recall=0.667, Specificity=0.967, Brier=0.071
- [x] Go/No-Go 判定: AUC/Specificity/Brier 达标, Recall=0.667 < 0.75（模型偏保守，高特异度；优化策略：调整 decision threshold 或 class_weight）
- [x] 保存: `mmpsy_lite_model.pkl` + `mmpsy_lite_scaler.pkl`
- [x] 导出: `mmpsy_lite_feature_names.json` + `mmpsy_lite_metrics.json`

### T-TRAIN-003: 备选模型 (LightGBM, P1)
- [x] 加载 lightgbm 成功
- [x] LGBMClassifier(max_depth=3, n_estimators=50) → CalibratedClassifierCV
- [x] GBDT AUC=0.928, F1=0.778 (略优于 LR)
- [x] 保存 `mmpsy_lite_model_gbdt.pkl`

### T-TRAIN-004: 生成训练报告与图表
- [x] 生成 ROC 曲线 → `mmpsy_lite_roc_curve.png`
- [x] 生成校准曲线 → `mmpsy_lite_calibration_curve.png`
- [x] 生成混淆矩阵热力图 → `mmpsy_lite_confusion_matrix.png`
- [x] 产出 `mmpsy_lite_training_report.md` (含 Go/No-Go 判定)

---

## Phase 3: 消融实验

### T-ABL-001: 实现消融实验脚本
- [x] 创建 `backend/scripts/modeling/v1_25/03_ablation_study.py`
- [x] 从 `mmpsy_lite_feature_names.json` 读取 `MODEL_FEATURES`
- [x] 定义 5 个消融配置 (A:PHQ-9, B:GAD-7, C:纯文本, D:GAD-7+文本, E:完整17维)
- [x] 实现 5-Fold CV 训练 + 评估 (StandardScaler per fold)
- [x] 实现 `compute_bootstrap_p()`: Bootstrap AUC 差异检验 (n=1000, 5-fold pooling)
- [x] 多重比较: Bonferroni α' = 0.05/4 = 0.005 (D/B, E/B, D/C, E/C)

### T-ABL-002: 运行消融实验
- [x] 运行 `03_ablation_study.py`
- [x] 5 配置 × 4 指标:
  - A(PHQ-9): AUC=1.000, F1=1.000 (理论上限)
  - B(GAD-7): AUC=0.920, F1=0.724, Recall=0.810 ⭐ 最佳非PHQ-9配置
  - C(文本): AUC=0.689, F1=0.435
  - D(GAD-7+文本): AUC=0.916, F1=0.698
  - E(完整17D): AUC=0.913, F1=0.702
- [x] 4 对比较 Bootstrap: 全部 p>>0.05，无显著差异

### T-ABL-003: 生成消融报告 + 科学发现
- [x] 产出 `ablation_results.json`
- [x] 产出 `ablation_report.md`
- [x] 🔬 **关键发现**: GAD-7 单独是最强信号(AUC=0.920)，文本关键词+人口学无显著增量。
  v1.25 lite 模型可用 GAD-7 为主体，文本特征作为辅助（非必要）。与 v1.23 mmpsy AUC=0.6249 对比，
  v1.25 在 mmpsy 数据上 AUC 提升 +0.295 (= +47%)。

---

## Phase 4: model_engine 路由改造

### T-ENG-001: 新增 LiteFeatureExtractor 类
- [x] 修改 `backend/app/core/model_engine.py`
- [x] 在文件顶部 `class ModelEngine` 之前新增 `LiteFeatureExtractor` 类
- [x] 内嵌 `KEYWORD_CATEGORIES` 字典 (7 类，与 01_build_lite_features 完全一致)
- [x] 实现 `extract(transcript)` 静态方法 → {keyword_counts, total_keywords, unique_categories}
- [x] self_harm_crisis 类别计数 ×2 加权

### T-ENG-002: 新增 LITE_FEATURE_ORDER + predict_lite()
- [x] 在文件顶部定义 `LITE_FEATURE_ORDER` 列表 (17 元素)
- [x] 在 ModelEngine 类中新增 `predict_lite()` 异步方法
- [x] 实现文本质量检测 (length < 20 → 回退)
- [x] 实现关键词提取 → 特征向量构建 (17 维)
- [x] 实现模型推理: load model + scaler → transform → predict_proba → score
- [x] 模型加载失败 → 自动回退 _anxiety_only_fallback()

### T-ENG-003: 新增 _anxiety_only_fallback()
- [x] 在 predict_lite 之后新增 `_anxiety_only_fallback(gad7_score)` 方法
- [x] 经验映射: PHQ-9_estimated = min(gad7 × 1.29, 27.0)
- [x] risk_score = estimated / 27.0 × 100
- [x] 返回 model_family="fallback", fallback_used=True, fallback_reason 字段

### T-ENG-004: 路由分派 + routing_info 追加
- [x] 在 `predict_structured()` 入口插入路由决策代码块
- [x] 定义 `STRUCTURED_FEATURE_SET` (14 特征) + 计算 f_coverage
- [x] f_coverage ≥ 0.80 → structured 路径 (设置 routing_info, 继续原逻辑)
- [x] GAD-7 + text ≥ 20 → 调用 predict_lite(), 早期返回
- [x] 仅 GAD-7 → 调用 _anxiety_only_fallback(), 早期返回
- [x] 都不满足 → 返回 insufficient 结果
- [x] 在 result 构建完成后追加 `result["routing_info"] = routing_info`

---

## Phase 5: 注册表注册

### T-REG-001: 注册 v1.25 lite 模型
- [x] 修改 `backend/app/core/model_registry.py`
- [x] `MODEL_PATHS` 新增: `mmpsy_lite_model`, `mmpsy_lite_scaler`, `mmpsy_lite_gbdt`
- [x] `MODEL_REGISTRY` 新增: `mmpsy_lite_model` (lifecycle=candidate, 17 features, excluded_inputs=["phq9_score"], label=phq9_binary)
- [x] `MODEL_REGISTRY` 新增: `mmpsy_lite_scaler` (lifecycle=candidate)

---

## Phase 6: Schema + Service 层

### T-SCH-001: 新增 RoutingInfo Schema
- [x] 修改 `backend/app/schemas/model_predict.py`
- [x] 新增 `RoutingInfo` Pydantic model (5 字段: selected_model_id, selected_model_family, routing_reason, feature_coverage_ratio, prediction_confidence_band)

### T-SVC-001: Service 路由日志
- [x] 修改 `backend/app/services/model_predict_service.py`
- [x] `predict_tabular()` 方法中: 从 result 提取 routing_info
- [x] 添加路由决策 info 日志 (family, reason, coverage, band)

---

## Phase 7: 前端改造

### T-FE-001: API 类型更新
- [x] 修改 `frontend/src/api/modelApi.ts`
- [x] 新增 `RoutingInfo` interface (5 字段)
- [x] `ModelPredictResponse` interface 新增 `routing_info: RoutingInfo | null`

### T-FE-002: 路由透明展示
- [x] 修改 `frontend/src/views/user/UserRiskPage.vue`
- [x] 在风险评估结果卡片顶部增加路由透明展示区块 (family + reason + confidence tag)
- [x] 实现 `routeFamilyLabel()`, `routeReasonLabel()`, `confidenceTagType()`, `confidenceLabel()` 辅助函数，以及 `routeFamilyTagType()`
- [x] structured 用户仅显示路由信息行 (无额外卡片)
- [x] anxiety_only / insufficient 用户显示回退说明

### T-FE-003: 实验参考 3 卡片
- [x] 当 `selected_model_family === "lite"` 时显示 "实验参考 3 — v1.25 mmpsy-lite 专用模型" 卡片
- [x] 卡片内容: risk_score, probability, 免责声明
- [x] 卡片样式: 虚线边框 + 警告色背景

---

## Phase 8: 配置项

### T-CFG-001: 新增路由配置
- [x] 修改 `backend/app/core/config.py`
- [x] 新增 `route_feature_coverage_threshold: float = 0.80`
- [x] 新增 `route_lite_min_text_length: int = 20`

---

> **总计**: 22 个任务 | Phase 0-8 | 严格按物理顺序执行

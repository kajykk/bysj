# v1.24 开发任务列表

> **迭代**: v1.24-mmpsy-external-consistency-and-score-stability
> **日期**: 2026-05-02 | **基线**: Round 3 Locked
> **执行铁律**: 必须按物理顺序执行，严禁跳跃

---

## Phase 0: 资产审计

### T-ASSET-001: 创建并运行资产检查脚本
- [x] 创建 `backend/scripts/modeling/v1_24/00_asset_check.py`
- [x] 实现 9 项资产的存在性检查 (参考 03-design.md §1.1)
- [x] 实现 delta CSV 完整性验证 (4318 行 / 19 列 / mean_abs_delta ≈ 21.29)
- [x] 运行脚本: `python 00_asset_check.py`
- [x] 产出 `asset_check_report.md`，所有 9 项 ✅

---

## Phase 1: mmpsy 特征构建

### T-FEAT-001: 实现 mmpsy 特征构建脚本
- [x] 创建 `backend/scripts/modeling/v1_24/01_build_mmpsy_features.py`
- [x] 实现 `count_keywords()`, `check_crisis()`, `derive_sleep_duration()`, `derive_stress()`, `derive_anxiety()`
- [x] `SLEEP_RULES` 按 key 长度降序遍历 (防子串冲突)
- [x] 实现 12 特征的逐列构建 (参考 03-design.md §1.2)
- [x] 添加 `_source` 来源标注列 (derived/imputed)
- [x] pandas apply 使用 lambda 包装传参

### T-FEAT-002: 运行特征构建并生成报告
- [x] 运行 `01_build_mmpsy_features.py`
- [x] 产出 `data/processed/mmpsy_structured_features.csv` (1275 × 24)
- [x] 产出 `mmpsy_feature_mapping_report.md`
- [x] 产出 `mmpsy_missingness_report.md`
- [x] 验证覆盖率统计 (derived 特征数 / 12)

---

## Phase 2: mmpsy 受限外部验证

### T-VAL-001: 实现 mmpsy 验证脚本
- [x] 创建 `backend/scripts/modeling/v1_24/02_validate_mmpsy.py`
- [x] 加载 v1.23 pipeline + 通过 `pipeline.feature_names_in_` 获取特征顺序
- [x] 预测 1275 样本，以 phq9_binary 为 ground truth
- [x] 计算: AUC, Precision, Recall, F1, Specificity, 混淆矩阵
- [x] 计算: Pearson r (vs phq9_score), Spearman ρ (vs gad7_score)
- [x] 计算: 高风险召回率

### T-VAL-002: 有效特征子集基线
- [x] 训练微型 3 特征 LR (stress_level, anxiety, panic_attack)
- [x] 5-fold CV 计算 AUC_3feature
- [x] 计算 AUC_gap = AUC_12feature - AUC_3feature

### T-VAL-003: 运行验证并生成报告
- [x] 运行 `02_validate_mmpsy.py`
- [x] 产出 `mmpsy_external_validation_metrics.json`
- [x] 产出 `mmpsy_external_validation_report.md` (含受限声明)
- [x] 产出 ROC 曲线和校准曲线 PNG

---

## Phase 3: Delta 分层分析

### T-DELTA-001: 实现 delta 分析脚本
- [x] 创建 `backend/scripts/modeling/v1_24/03_analyze_delta.py`
- [x] 使用正确列名 (`v120_risk`, `v123_risk`, `delta_v123_v120`, `depression_binary`)
- [x] 实现 6 层分析 (Level 1-6, 参考 03-design.md §1.4)
- [x] 分段点推荐使用五分位数法

### T-DELTA-002: 运行分析并生成报告
- [x] 运行 `03_analyze_delta.py`
- [x] 产出 `delta_distribution_report.md`
- [x] 产出 `delta_by_risk_group.csv`, `delta_by_feature_group.csv`, `extreme_delta_cases.csv`
- [x] 验证全局统计与已知基线一致 (Mean Abs Delta = 21.29)

---

## Phase 4: Score Adapter

### T-ADAPT-001: 实现 ScoreAdapter 类
- [x] 创建 `backend/scripts/modeling/v1_24/04_train_adapter.py`
- [x] 实现 `ScoreAdapter` 类 (参考 02-architecture.md §3.5)
- [x] 实现 `transform()`, `_find_segment()`, `_near_boundary()`, `_smooth()`, `_label()`
- [x] Adapter config 不含 intercept 字段

### T-ADAPT-002: 训练 Adapter
- [x] 从 `delta_by_risk_group.csv` 加载分段点
- [x] 构建 config → ScoreAdapter(config)
- [x] 全量验证 (4318 样本): 计算 new_mean_abs_delta, auc_loss

### T-ADAPT-003: Pareto 前沿实验
- [x] 对 4 个 slope 乘数候选 [0.3, 0.5, 0.7, 0.9] 做对比
- [x] 产出 `adapter_experiment_results.csv` (trade-off 曲线)
- [x] 产出 `adapter_selection_report.md` (推荐配置 + 理由)

### T-ADAPT-004: 保存 Adapter
- [x] 创建 `backend/models/v1.24_adapter/` 目录
- [x] `joblib.dump(adapter, "score_adapter.pkl")`
- [x] 保存 `score_adapter_config.json`
- [x] 验收: Mean Abs Delta < 15, AUC 损失 ≤ 0.02 (或输出 Pareto 前沿说明)

---

## Phase 5: model_engine Shadow 接入

### T-ENG-001: v1.21 实验路径 lifecycle 包裹
- [x] 修改 `model_engine.py` L530 前: 插入 lifecycle 检查
- [x] 当 `lifecycle == "deprecated"` → 跳过整个 v1.21 实验块
- [x] 不改动 L559-562 结果字段初始化

### T-ENG-002: 新增 v1.24 Adapter 路径
- [x] 在 `model_engine.py` L604 后新增 adapter 代码块
- [x] 实现 `_load_adapter()` 方法
- [x] 在 result dict 中增加 6 个新字段

### T-ENG-003: 监控持久化
- [x] `__init__` 增加 `_start_time`, `_persist_task`, `_snapshot_path`
- [x] 实现 `_persist_loop()`, `start_persist()`, `stop_persist()`
- [x] `get_metrics_snapshot()` 增加 `uptime_seconds`, `delta_by_level`
- [x] 快照路径使用绝对路径 (`Path(__file__).resolve().parents[2] / "logs"`)

### T-ENG-004: 启动入口集成
- [x] 修改 `main.py` lifespan: 加入 `start_persist()` / `stop_persist()`
- [x] 如不可行，降级为 `@app.on_event("startup")` 调用

---

## Phase 6: 前端展示优化

### T-FE-001: API 类型更新
- [x] `modelApi.ts` ModelPredictResponse 新增 6 个字段类型

### T-FE-002: UI 展示 v1.24 适配分
- [x] `UserRiskPage.vue` "实验参考 2" 卡片增加 v1.24 适配分行
- [x] 实现 `migrationTagType()`, `migrationLabel()` 辅助函数
- [x] 迁移安全标签颜色: stable=success, slight_diff=primary, marked_diff=warning, review=danger

---

## Phase 7: 注册表治理

### T-REG-001: 新增 lifecycle 枚举
- [x] `model_registry.py` 新增 `StrEnum ModelLifecycle` (5 个值)
- [x] `ModelMetadata` dataclass 增加 `lifecycle` 字段 (默认 EXPERIMENTAL)

### T-REG-002: 分配生命周期
- [x] 逐模型设置 lifecycle (参考 03-design.md §3.2)
- [x] 注册 v1.24_adapter (lifecycle=CANDIDATE)

### T-REG-003: 前端隐藏 deprecated/disabled
- [x] 前端模型展示逻辑: lifecycle 为 deprecated/disabled 的模型不显示

---

## Phase 8: 灰度资格评估

### T-DEC-001: 决策文档
- [x] 汇总 Phase 2 验证结果 + Phase 5 delta 指标
- [x] 根据决策分级矩阵给出推荐
- [x] 产出 `v1_24_go_no_go_recommendation.md`

---

> **总计**: 22 个任务 | Phase 0-8 | 严格按物理顺序执行

# v1.26 测试计划

> **迭代编号**: v1.26-lite-recall-optimization-and-active-readiness
> **状态**: Round 1 / Step 1 — Draft v1
> **前置**: [04-ralph-tasks.md](file:///e:/code/bysj/docs/planning/v1.26-lite-recall-optimization-and-active-readiness/04-ralph-tasks.md)
> **执行铁律**: 按物理顺序执行，每完成一项立即更新状态

---

## Phase 0: 基线复现

### [TC-REPRO-HP-001] 基线指标复现偏差检查 (P0)
- [ ] 运行 `00_reproduce_baseline.py`
- [ ] AUC 与 v1.25 偏差 ≤ 0.01
- [ ] Recall 与 v1.25 偏差 ≤ 0.03
- [ ] Specificity 与 v1.25 偏差 ≤ 0.03

### [TC-REPRO-EC-002] 数据分割一致性 (P0)
- [ ] 测试集样本数 = 192
- [ ] 阳性率与 v1.25 一致
- [ ] split 记录到 `v1_25_test_split_snapshot.csv`

### [TC-REPRO-SP-003] 输出文件完整性 (P0)
- [ ] `v1_26_baseline_metrics.json` 存在且非空
- [ ] `v1_26_baseline_reproduction_report.md` 存在且含对比表

---

## Phase 1: Threshold 优化

### [TC-THRSH-HP-001] 阈值扫描完整覆盖 (P0)
- [ ] 运行 `01_threshold_sweep.py`
- [ ] 覆盖 8 个阈值：0.15, 0.20, ..., 0.50
- [ ] 每个阈值产出 Precision / Recall / F1 / Specificity / Confusion Matrix

### [TC-THRSH-HP-002] 关键点识别正确 (P0)
- [ ] Youden J 最大点被标记
- [ ] Recall ≥ 0.75 下 Specificity 最高点被标记
- [ ] F1 最大点被标记

### [TC-THRSH-EC-003] 极端阈值行为 (P1)
- [ ] threshold = 0.15 → Recall 接近 1.0，Specificity 不应为 0
- [ ] threshold = 0.50 → Recall ≤ v1.25 基线（默认阈值效果）

### [TC-THRSH-UI-004] 图表文件生成 (P1)
- [ ] `precision_recall_curve.png` 存在且 > 10 KB
- [ ] `threshold_vs_recall_specificity.png` 存在且 > 10 KB

### [TC-THRSH-SP-005] 选定阈值配置有效性 (P0)
- [ ] `selected_threshold_config.json` 存在
- [ ] 选择理由字段非空
- [ ] threshold ∈ [0.15, 0.50]

---

## Phase 2: Class Weight 训练

### [TC-CLW-HP-001] 6 个候选模型全训练 (P0)
- [ ] 运行 `02_train_recall_optimized.py`
- [ ] 6 个候选 (balanced / w1.5 / w2 / w3 / Calibrated+threshold / GBDT+threshold) 全部产出指标
- [ ] `recall_optimized_model_results.csv` 含 6 行数据

### [TC-CLW-HP-002] 指标在有效范围内 (P0)
- [ ] 所有 AUC ∈ [0.5, 1.0]
- [ ] 所有 Recall / Specificity / F1 ∈ [0, 1]

### [TC-CLW-SP-003] 与 v1.25 基线对比逻辑 (P0)
- [ ] `model_selection_rationale.md` 含逐条件对比表
- [ ] AUC 不降 >0.03 条件被检查
- [ ] 明确推荐：保留原模型 / 替换为新模型

### [TC-CLW-EC-004] class_weight 极端值不崩溃 (P1)
- [ ] class_weight={0:1,1:3} 训练不抛出异常
- [ ] Specificity 不降至 0（极端偏向不应导致所有样本预测为阳性）

---

## Phase 3: 路由稳定性

### [TC-ROUTE-HP-001] 全特征输入 → structured (P0)
- [ ] 14/14 特征提供 + text → family="structured"
- [ ] band="high"

### [TC-ROUTE-HP-002] GAD7 + text → lite (P0)
- [ ] gad7 + text≥20chars → family="lite"
- [ ] band="medium"

### [TC-ROUTE-HP-003] 仅 GAD7 → anxiety_only (P0)
- [ ] 仅 gad7=15 → family="anxiety_only"
- [ ] band="low"
- [ ] fallback_used=True

### [TC-ROUTE-HP-004] 空输入 → insufficient (P0)
- [ ] 空 dict → family="insufficient"
- [ ] risk_score=None
- [ ] warning 非空

### [TC-ROUTE-SP-005] routing_info 完整性 (P0)
- [ ] 4 条路径下 routing_info 均非 null
- [ ] 每条含 5 字段：model_id / family / reason / coverage / band

### [TC-ROUTE-EC-006] 全特征 + 空 text → structured (P0)
- [ ] 14/14 特征 + text="" (或缺失) → 仍应为 structured（因为 f_coverage 够）
- [ ] 不降级到 lite

### [TC-ROUTE-EC-007] Lite 文本边界 (P1)
- [ ] text 正好 20 chars → 不 fallback
- [ ] text 19 chars → fallback (text_insufficient)
- [ ] text < 20 且 gad7 不可用 → insufficient

### [TC-ROUTE-SP-008] 输出文件完整性 (P0)
- [ ] `routing_stability_report.md` 存在
- [ ] `routing_distribution_snapshot.csv` 存在
- [ ] `routing_edge_cases.csv` 存在

---

## Phase 4: Lifecycle 治理

### [TC-LFC-HP-001] limited_active 状态可注册 (P0)
- [ ] 在 `model_registry.py` 中新增 `limited_active` 枚举值
- [ ] `LifecycleState("limited_active")` 构造成功

### [TC-LFC-HP-002] get_active_models 排除 disabled (P0)
- [ ] disabled 模型不出现于 `get_active_models()` 返回列表
- [ ] deprecated 模型不出现于面向普通用户的列表

### [TC-LFC-SP-003] 7 模型 lifecycle 全部定义 (P0)
- [ ] `model_lifecycle_decision_report.md` 含全部 7 个模型的状态
- [ ] 无 "未定义" 状态的模型

### [TC-LFC-EC-004] default 模型始终可回退 (P1)
- [ ] v1.20 不因 lifecycle 变更而失去 default 状态
- [ ] 系统启动后 default 模型始终可调用

---

## Phase 5: 监控面板

### [TC-MON-HP-001] 内存计数器初始化 (P0)
- [ ] `ModelEngine()` 构造后 `_routing_stats` 初始化为 全 0
- [ ] `_fallback_count` = 0
- [ ] `_crisis_override_count` = 0

### [TC-MON-HP-002] 路由分派计数累加 (P1)
- [ ] 调用 `predict_structured(full_features)` → `_routing_stats["structured"]` += 1
- [ ] 调用 `predict_structured(lite_features)` → `_routing_stats["lite"]` += 1
- [ ] 调用 `predict_structured(anxiety_only_features)` → `_routing_stats["anxiety_only"]` += 1

### [TC-MON-SP-003] get_metrics_snapshot 返回结构化数据 (P1)
- [ ] `engine.get_metrics_snapshot()` 返回 dict
- [ ] 含 routing / fallback_count / crisis_override_count / timestamp
- [ ] `/api/metrics/snapshot` 返回 200 + JSON

---

## Phase 6: Crisis Safety Override

### [TC-SAF-HP-001] "想死" 触发 crisis (P0)
- [ ] text="我不想活了想死" → safety_flags=["crisis_keyword_detected"]
- [ ] requires_human_review=True

### [TC-SAF-HP-002] "自杀" 触发 crisis (P0)
- [ ] text="我有自杀倾向" → safety_flags=["crisis_keyword_detected"]
- [ ] risk_level ≥ 3（即使模型预测更低）

### [TC-SAF-HP-003] "自残" 触发 crisis (P0)
- [ ] text="我经常自残" → safety_flags=["crisis_keyword_detected"]

### [TC-SAF-HP-004] Crisis + 低 GAD-7 仍需复核 (P0)
- [ ] text="想死" + gad7=2 → requires_human_review=True, risk_level=3
- [ ] 不被低 GAD-7 覆盖

### [TC-SAF-HP-005] 非 crisis 文本不触发 (P0)
- [ ] text="失眠睡不着考试压力大心情差" → safety_flags=[], requires_human_review=False

### [TC-SAF-EC-006] Crisis 检测不依赖模型 (P0)
- [ ] 临时禁用模型 → `_check_crisis_safety("想死")` 仍返回 crisis
- [ ] safety 逻辑在 try/except 之前执行

### [TC-SAF-SP-007] "压力很大但还能坚持" 不触发 (P1)
- [ ] 含"压力"但不含 crisis 词 → 不触发

### [TC-SAF-EC-010] "不如死了算了" 触发 crisis (P1)
- [ ] 扩展关键词 "死了算了" → 触发
- [ ] 验证 Simulation 发现的边界已修复

### [TC-SAF-UI-008] 前端人工复核提醒展示 (P0)
- [ ] requires_human_review=true → 页面显示 el-alert type="warning"
- [ ] 文案含 "建议人工复核"
- [ ] risk_score 正常展示（不被 alert 遮挡）

### [TC-SAF-SP-009] Schema 新字段向后兼容 (P1)
- [ ] safety_flags:[] 时旧版前端不崩溃
- [ ] requires_human_review 字段缺失时前端默认 false

---

## Phase 7: Config 验证

### [TC-CFG-HP-001] 新增配置项可读 (P0)
- [ ] `settings.lite_decision_threshold` 可访问
- [ ] `settings.crisis_keywords` 可访问，类型为 list[str]

### [TC-CFG-SP-002] 配置默认值与规范一致 (P0)
- [ ] `lite_decision_threshold` 默认值 = 0.50（或 Phase 1 选定值）
- [ ] `crisis_keywords` 默认值含 10 个关键词

---

### [TC-FE-HP-001] TypeScript 类型编译通过 (P0)
- [ ] `npx vue-tsc --noEmit` 零错误输出
- [ ] `npm run build` 成功

### [TC-FE-HP-002] Crisis alert 条件渲染 (P0)
- [ ] requires_human_review=true → alert 可见
- [ ] requires_human_review=false → alert 不可见
- [ ] routing_info=null → alert 不可见（不崩溃）

### [TC-FE-EC-003] Lifecycle 标签展示 (P1)
- [ ] lite 路径 → 显示 lifecycle="limited_active" 标签

---

## Phase 8: Go/No-Go

### [TC-GNG-HP-001] Go/No-Go 报告完整性 (P0)
- [ ] 运行 `04_go_no_go_report.py`
- [ ] 与 Go/No-Go 标准逐条比对
- [ ] `v1_26_go_no_go_recommendation.md` 含最终判定（GO / CONDITIONAL-GO / NO-GO）

---

> **总计**: 8 Phases / **36 测试用例**
> **分布**: P0 = 25 / P1 = 11

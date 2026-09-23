# v1.26 需求文档 (PRD)

> **迭代编号**: v1.26-lite-recall-optimization-and-active-readiness
> **中文名称**: 轻特征模型召回优化与 Active 就绪治理
> **状态**: Round 1 / Step 1 — Draft v1
> **前置依赖**: v1.25-mmpsy-lite-risk-model (DELIVERED, 2026-05-02)
> **输入来源**: `e:\code\bysj\md\9.md` (v1.26 提案)

---

## 目录

- [一、背景与定位](#一背景与定位)
- [二、核心目标](#二核心目标)
- [三、功能需求](#三功能需求)
- [四、非功能需求](#四非功能需求)
- [五、数据需求](#五数据需求)
- [六、Go / No-Go 准入标准](#六go--no-go-准入标准)
- [七、约束与边界](#七约束与边界)
- [八、附录](#八附录)

---

## 一、背景与定位

### 1.1 一句话定位

> **v1.26 是最后一轮实质性迭代：不扩大模型范围，仅做 Recall 优化、阈值治理、灰度观测、安全复核与生命周期收口。**

### 1.2 前置状态

| 项 | v1.25 交付结论 |
|---|---|
| 多模型路由体系 | structured / lite / anxiety_only / insufficient 四层闭环 |
| Lite 模型 AUC | 0.9380 ✅ |
| Lite 模型 Specificity | 0.9673 ✅ |
| Lite 模型 Recall | **0.6667 ⚠️** (Go/No-Go 阈值 0.75 未达标) |
| GAD-7 信号强度 | 消融实验确认为压倒性最强非 PHQ-9 信号 |
| 文本关键词增量 | 无统计显著增量（Bootstrap p>>0.05） |

### 1.3 v1.26 需要回答的 5 个问题

| # | 问题 | 期望答案 |
|---|------|---------|
| Q1 | Recall 能否从 0.6667 提升到 ≥ 0.75？ | Threshold 调整优先 |
| Q2 | 提升 Recall 后 Specificity 是否仍 ≥ 0.65？ | — |
| Q3 | 哪种策略最稳？ | Threshold > ClassWeight > Model |
| Q4 | 路由分派是否稳定？ | structured 不被误分到 lite |
| Q5 | 多模型体系可否进入最终封版？ | v1.26 达标后即封版 |

### 1.4 目标人群

与 v1.25 相同：mmpsy / 类 mmpsy 数据源，低结构化特征覆盖（f_coverage < 80%），提供 GAD-7 + 文本的轻特征人群。

---

## 二、核心目标

### 2.1 主目标

将 `v1.25 mmpsy-lite` 从 `candidate/shadow` 推进到 `limited-active` 或 `active-ready`，前提是召回率与灰度稳定性达标。

### 2.2 总体路线

> **Threshold-first, ClassWeight-second, Model-last**

| 优先级 | 策略 | 成本 | 风险 |
|:---:|---|:---:|:---:|
| 1 | 调整 decision threshold | 低 | 低 |
| 2 | class_weight 训练对比 | 中 | 中 |
| 3 | 切换 GBDT / Ensemble | 高 | 高 |

### 2.3 关键绩效指标

| 指标 | 当前值 (v1.25) | 必须达到 (MUST) | 推荐达到 (SHOULD) |
|---|---|---|---|
| Recall | 0.6667 | ≥ 0.75 | ≥ 0.78 |
| Specificity | 0.9673 | ≥ 0.65 | ≥ 0.75 |
| AUC | 0.9380 | ≥ 0.88 | ≥ 0.90 |
| Brier Score | 0.0710 | ≤ 0.12 | ≤ 0.10 |
| F1 | 0.7429 | ≥ 0.70 | ≥ 0.72 |
| Precision | 0.8387 | ≥ 0.55 | ≥ 0.60 |

---

## 三、功能需求

### 3.1 Phase 0：资产与基线复现 (FR-REPRO)

| ID | 需求 | 优先级 |
|---|---|---|
| FR-REPRO-01 | 复现 v1.25 测试集指标 (AUC, Recall, Specificity, F1) | P0 |
| FR-REPRO-02 | 固定测试集 split（种子、阳性率、样本 ID 与 v1.25 一致） | P0 |
| FR-REPRO-03 | 输出 baseline snapshot（指标 JSON + 报告 MD） | P0 |
| FR-REPRO-04 | 验证复现偏差 ≤ 0.01 (AUC) / 0.03 (Recall/Specificity) | P0 |

**输入**：
- `backend/models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl`
- `backend/models/v1.25_mmpsy_lite/mmpsy_lite_scaler.pkl`
- v1.25 训练/特征构建脚本

**产出**：
- `v1_26_baseline_reproduction_report.md`
- `v1_26_baseline_metrics.json`
- `v1_25_test_split_snapshot.csv`

### 3.2 Phase 1：Decision Threshold 优化 (FR-THRESH)

| ID | 需求 | 优先级 |
|---|---|---|
| FR-THRESH-01 | 对 v1.25 模型（不重训）扫描 8 个阈值：0.15 ~ 0.50（步长 0.05） | P0 |
| FR-THRESH-02 | 记录每个阈值的 Precision / Recall / F1 / Specificity / 混淆矩阵 | P0 |
| FR-THRESH-03 | 识别 Youden J 最大点、Recall ≥ 0.75 下 Specificity 最高点、F1 最大点 | P0 |
| FR-THRESH-04 | 生成 Precision-Recall 曲线图 | P1 |
| FR-THRESH-05 | 生成 threshold vs Recall/Specificity 双轴图 | P1 |
| FR-THRESH-06 | 输出 selected_threshold_config.json（含选择理由） | P0 |

**推荐选择策略**（优先级从高到低）：
1. Recall ≥ 0.75 且 Specificity ≥ 0.65 的阈值中 F1 最高者
2. 若无满足条件者 → 选择 Recall ≥ 0.75 条件下 Specificity 最高者
3. 若仍不满足 → 进入 Phase 2

**产出**：
- `threshold_sweep_results.csv`
- `threshold_selection_report.md`
- `precision_recall_curve.png`
- `threshold_vs_recall_specificity.png`
- `selected_threshold_config.json`

### 3.3 Phase 2：Class Weight 与召回增强训练 (FR-CLW)

| ID | 需求 | 优先级 |
|---|---|---|
| FR-CLW-01 | 训练 4 组 LR class_weight 变体：balanced / {0:1,1:1.5} / {0:1,1:2} / {0:1,1:3} | P0 |
| FR-CLW-02 | 训练 1 组 Calibrated LR + selected threshold 组合 | P1 |
| FR-CLW-03 | 训练 1 组 GBDT shallow + selected threshold 组合 | P2 |
| FR-CLW-04 | 所有变体使用与 v1.25 相同的 17 维特征和训练/测试分割 | P0 |
| FR-CLW-05 | 对比表含 AUC / Recall / Specificity / Precision / F1 / Brier | P0 |
| FR-CLW-06 | 选择理由文档 (model_selection_rationale.md) | P0 |

**替换条件**：只有新模型同时满足以下条件，才建议替换 v1.25 当前模型：
- AUC 不低于 v1.25 超过 0.03
- Recall ≥ 0.75
- Specificity ≥ 0.65
- Brier 无明显变差（增幅 ≤ 0.03）
- 解释性不低于 LR 当前方案

**产出**：
- `recall_optimized_model_results.csv`
- `recall_optimized_training_report.md`
- `mmpsy_lite_recall_model.pkl`（如确实优于原模型）
- `model_selection_rationale.md`

### 3.4 Phase 3：Lite 路由稳定性评估 (FR-ROUTE)

| ID | 需求 | 优先级 |
|---|---|---|
| FR-ROUTE-01 | 统计四层路由分派分布（每层样本数与占比） | P0 |
| FR-ROUTE-02 | 检查 structured 用户是否被误分到 lite（目标 0 例） | P0 |
| FR-ROUTE-03 | 检查 lite 用户是否因短文本被过多分到 anxiety_only | P1 |
| FR-ROUTE-04 | 统计 routing_reason 分布 | P0 |
| FR-ROUTE-05 | 统计 fallback_used_rate（目标 < 5%） | P0 |
| FR-ROUTE-06 | 验证 routing_info 完整率 = 100%（4 路径 × 5 字段） | P0 |
| FR-ROUTE-07 | 统计 anxiety_only 路径高风险比例 | P1 |
| FR-ROUTE-08 | 明确 insufficient 路径前端提示是否可达 | P1 |

**产出**：
- `routing_stability_report.md`
- `routing_distribution_snapshot.csv`
- `routing_edge_cases.csv`
- `routing_policy_v1_26.json`

### 3.5 Phase 4：模型生命周期晋级治理 (FR-LIFECYCLE)

| ID | 需求 | 优先级 |
|---|---|---|
| FR-LIFECYCLE-01 | 引入 lifecycle 状态：default / active / limited_active / candidate / experimental / deprecated / disabled | P0 |
| FR-LIFECYCLE-02 | 对系统中 7 个模型逐一给出 lifecycle 决策 | P0 |
| FR-LIFECYCLE-03 | disabled 模型不进入普通调用路径 | P0 |
| FR-LIFECYCLE-04 | deprecated 模型不展示给普通用户 | P1 |
| FR-LIFECYCLE-05 | 更新 model_registry.py 并同步前端模型状态展示 | P0 |

**推荐状态矩阵**（待 v1.26 验证后调整）：

| 模型 | 建议 lifecycle |
|---|---|
| v1.20 structured (全特征 LR) | `default` |
| v1.24 adapter | `limited_active` |
| v1.25 / v1.26 lite | `limited_active` |
| v1.23 external LR | `experimental` |
| v1.21 binary LR | `deprecated` |
| v1.21 multiclass | `disabled` |

> **硬约束**：v1.25/v1.26 lite 不设为全局 `default`，仅作为特定路由场景的 `limited_active`。

**产出**：
- `model_lifecycle_decision_report.md`
- `model_registry_v1_26_update.md`
- 更新 `model_registry.py`
- 更新前端模型状态展示（如有）

### 3.6 Phase 5：灰色观测面板 (FR-MONITOR)

| ID | 需求 | 优先级 |
|---|---|---|
| FR-MONITOR-01 | 路由层：记录 structured / lite / anxiety_only / insufficient 计数 | P0 |
| FR-MONITOR-02 | 模型层：记录 lite 预测总数、错误率、延迟 (ms)、风险分均值、高风险率 | P0 |
| FR-MONITOR-03 | 安全层：记录 self_harm 关键词命中数、high_risk_override 次数 | P0 |
| FR-MONITOR-04 | 后端扩展 `get_metrics_snapshot` API 端点 | P1 |
| FR-MONITOR-05 | 前端/管理端展示指标仪表盘（如已有管理页则集成） | P2 |
| FR-MONITOR-06 | 从 v1.25 模型运行时日志中提取路由分派分布 | P1 |

**观察周期建议**：
- 7 天：最小 shadow 观察
- 14 天：limited-active 前推荐观察
- 30 天：正式 active 决策更稳

**产出**：
- `monitoring_metrics_spec.md`
- `metrics_snapshot_v1_26.json`（基于已有日志/模拟数据）
- `shadow_observation_report_template.md`
- 后端 `get_metrics_snapshot` 扩展（可选）

### 3.7 Phase 6：高风险安全策略增强 (FR-SAFETY)

| ID | 需求 | 优先级 |
|---|---|---|
| FR-SAFETY-01 | 检测文本中 crisis 关键词：想死 / 自杀 / 自残 / 活不下去 / 不想活 / 结束生命 | P0 |
| FR-SAFETY-02 | 命中 crisis → safety_flag = true | P0 |
| FR-SAFETY-03 | 命中 crisis → risk_level 至少提升到中高风险 | P0 |
| FR-SAFETY-04 | 命中 crisis → 前端显示"需人工复核" | P0 |
| FR-SAFETY-05 | 后端记录 `self_harm_keyword_detected` 计数 | P1 |
| FR-SAFETY-06 | 输出字段：safety_flags / requires_human_review / crisis_keyword_detected / risk_override_reason | P0 |
| FR-SAFETY-07 | crisis + 低 GAD-7 仍需触发人工复核 | P0 |

**产出**：
- `safety_override_policy.md`
- 后端 safety override 逻辑（在 `model_engine.py` 或 `predict_lite()`）
- 前端人工复核提示（在 `UserRiskPage.vue`）
- 测试用例：crisis 文本必须触发复核

---

## 四、非功能需求

### 4.1 性能

| ID | 需求 | 阈值 |
|---|------|:---:|
| NFR-PERF-01 | lite 模型推理延迟 | < 50ms |
| NFR-PERF-02 | routing_info 计算延迟 | 不增加 > 1ms |
| NFR-PERF-03 | threshold sweep 执行时间 | < 10s（纯推理，不训练） |

### 4.2 可靠性

| ID | 需求 | 阈值 |
|---|------|:---:|
| NFR-REL-01 | lite 模型加载失败 → 自动回退到 anxiety_only_fallback | 100% 覆盖 |
| NFR-REL-02 | routing_info 在任何路径下都存在且完整 | 100% |
| NFR-REL-03 | crisis safety override 不依赖模型加载状态 | 始终可用 |

### 4.3 兼容性

| ID | 需求 |
|---|------|
| NFR-COMPAT-01 | 新增字段（safety_flags 等）对 v1.25 响应格式向后兼容 |
| NFR-COMPAT-02 | routing_info=null 时前端不崩溃（已在 v1.25 验证） |
| NFR-COMPAT-03 | lifecycle 新增状态对 model_registry 现有条目无破坏 |

### 4.4 可观测性

| ID | 需求 |
|---|------|
| NFR-OBS-01 | 所有 safety override 事件可日志追溯 |
| NFR-OBS-02 | fallback 事件含触发原因与输入数据摘要 |
| NFR-OBS-03 | 路由分派指标可按日/周粒度统计 |

---

## 五、数据需求

### 5.1 数据来源

与 v1.25 完全一致：
- `data/raw/mmpsy_scores.csv`（1,275 行，9 列）
- `data/raw/mmpsy_structured_features.csv`（结构化特征，用于路由测试）
- v1.25 已构建的 `data/processed/v1_25_lite_features.csv`（21 列）

### 5.2 训练/测试分割

| 项 | 约束 |
|---|------|
| test_size | 0.15 |
| random_state | 42 |
| stratify | phq9_binary |
| 训练集 | 1,083 |
| 测试集 | 192 |

> **强制**：v1.26 所有训练必须与 v1.25 使用相同的 split，确保可比性。

### 5.3 新增数据需求

| 项 | 说明 |
|---|------|
| crisis 关键词列表 | 在 LiteFeatureExtractor 中新增 `CRISIS_KEYWORDS` 常量 |
| lifecycle 状态枚举 | 新增 `limited_active` 状态值 |
| 监控指标结构 | JSON 格式的路由/模型/安全指标快照 |

---

## 六、Go / No-Go 准入标准

### 6.1 GO — Limited Active

| 条件 | 阈值 |
|---|---|
| Lite Recall | ≥ 0.75 |
| Lite Specificity | ≥ 0.65 |
| Lite AUC | ≥ 0.88 |
| Brier Score | ≤ 0.12 |
| crisis safety override | 通过 |
| 路由稳定 | structured → lite 误分 = 0 |
| fallback_used_rate | 可统计且可解释 |
| 前后端测试 | 通过 |

> **结论**：v1.25/v1.26 lite 可在 mmpsy-like 路由场景下进入 `limited_active`。

### 6.2 CONDITIONAL-GO — Continue Shadow

| 条件 |
|---|
| AUC 高但 Recall 在 0.70–0.75 |
| 或 routing 有轻微边界问题 |
| 或需要更多线上反馈 |

> **结论**：保持 candidate/shadow，继续观察，不进入 active。

### 6.3 NO-GO — Data Required

| 条件 |
|---|
| Recall 无法达标 |
| Specificity < 0.65 |
| 阈值调整导致误报过高 |
| 路由不稳定 |
| crisis safety 失败 |

> **结论**：不继续模型微调，转向补充数据或人工复核流程。

---

## 七、约束与边界

### 7.1 不使用/不引入

| 项 | 原因 |
|---|---|
| X 重型文本模型（BERT 等） | 样本仅 1,275；消融实验已证明文本无显著增量 |
| X 深度学习 | 同上；且增加上线与解释成本 |
| X SMOTE 或其他合成采样 | v1.25 规则：SMOTE 采样比例 ≤ 0.8:1；阈值调整已可处理 Recall |
| X 新特征维度扩展 | v1.25 17维已足够；v1.26 不扩大特征空间 |
| X lite 设为全局 default | lite 仅适用 mmpsy-like 轻特征场景 |

### 7.2 必须保留

| 项 | 原因 |
|---|---|
| v1.20 全特征 LR | 继续作为 default fallback |
| v1.24 adapter | 作为 structured candidate |
| PHQ-9 五层泄漏防护 | 与 v1.25 一致 |

### 7.3 与 v1.25 的关系

| 维度 | 关系 |
|---|---|
| 特征空间 | 不变（17 维） |
| 训练数据 | 不变（同源 mmpsy_scores） |
| 模型架构基座 | 不变（LR CalibratedClassifierCV），仅调参 |
| 路由架构 | 不变（4 层），仅评估稳定性 |
| 前端框架 | 增量添加 safety tips + lifecycle 展示 |

---

## 八、附录

### A. 需求追溯矩阵

| 功能需求 | 对应 Phase | 对应 v1.26 提案章节 | 优先级 |
|---|---|---|---|
| FR-REPRO-01 ~ 04 | Phase 0 | 四、Phase 0 | P0 |
| FR-THRESH-01 ~ 06 | Phase 1 | 四、Phase 1 | P0 |
| FR-CLW-01 ~ 06 | Phase 2 | 四、Phase 2 | P0 |
| FR-ROUTE-01 ~ 08 | Phase 3 | 四、Phase 3 | P0 |
| FR-LIFECYCLE-01 ~ 05 | Phase 4 | 四、Phase 4 | P0 |
| FR-MONITOR-01 ~ 06 | Phase 5 | 四、Phase 5 | P1 |
| FR-SAFETY-01 ~ 07 | Phase 6 | 四、Phase 6 | P0 |

### B. 缩写速查

| 缩写 | 全称 |
|---|---|
| LR | Logistic Regression |
| GBDT | Gradient Boosted Decision Trees (LightGBM) |
| CV | Cross-Validation |
| AUC | Area Under the ROC Curve |
| Brier | Brier Score (校准指标) |

### C. 参考文档

| 文档 | 路径 |
|---|---|
| v1.26 提案 | `e:\code\bysj\md\9.md` |
| v1.25 需求 | `docs/planning/v1.25-mmpsy-lite-risk-model/01-requirements.md` |
| v1.25 架构 | `docs/planning/v1.25-mmpsy-lite-risk-model/02-architecture.md` |
| v1.25 设计 | `docs/planning/v1.25-mmpsy-lite-risk-model/03-design.md` |
| v1.25 交付报告 | `docs/planning/v1.25-mmpsy-lite-risk-model/DELIVERY_REPORT.md` |
| Ralph 执行铁律 | `.trae/rules/Ralph.md` |

---

> **文档版本**: v1 (Draft)
> **创建日期**: 2026-05-02
> **下一动作**: Step 2 — Critique 深度自查

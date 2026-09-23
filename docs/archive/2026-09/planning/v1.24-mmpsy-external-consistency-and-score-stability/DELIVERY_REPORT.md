# v1.24 迭代交付报告 (Delivery Report)

> **迭代**: v1.24-mmpsy-external-consistency-and-score-stability
> **中文名**: mmpsy 外部一致性验证与风险评分迁移稳定性治理
> **交付日期**: 2026-05-02
> **最终决策**: **CONDITIONAL-GO — Shadow Mode**
> **上一迭代**: v1.23-external-risk-model-upgrade (已交付)

---

## 一、迭代概述

v1.24 是 v1.23 外部风险模型升级的延续，聚焦两个核心问题：

1. **mmpsy 外部一致性验证** — v1.23 模型在跨人群（mmpsy 1275 样本）上的泛化能力如何？
2. **评分迁移稳定性治理** — v1.20→v1.23 分数迁移 delta 高达 21.29，如何安全平滑过渡？

---

## 二、核心指标仪表盘

### 2.1 外部一致性 (mmpsy, N=1,275)

| 指标 | 值 | 阈值 | 判定 |
|------|:---:|:---:|:---:|
| AUC | 0.6249 | ≥ 0.80 | ❌ |
| Recall | 0.6860 | ≥ 0.75 | ⚠️ |
| Specificity | 0.4887 | ≥ 0.65 | ❌ |
| F1 | 0.3707 | — | — |
| Pearson r (vs PHQ-9) | 0.2151 | ≥ 0.50 | ❌ |
| Spearman ρ (vs GAD-7) | 0.1239 | ≥ 0.40 | ❌ |
| 特征覆盖率 | 50.0% (6/12) | ≥ 70% | ❌ |

### 2.2 Delta 压缩效果 (训练集, N=4,318)

| 指标 | Adapter 前 | Adapter 后 | 变化 |
|------|:---:|:---:|:---:|
| Mean Abs Delta | 21.29 | **4.37** | ↓ 79.5% |
| AUC | 0.9131 | **0.8934** | ↓ 0.0196 |
| |delta| > 15 | 47.1% | 0% | ↓ 100% |
| |delta| > 30 | 26.8% | 0% | ↓ 100% |
| stable 标签 | — | 10.6% | — |
| slight_diff 标签 | — | 89.0% | — |
| marked_diff / review | — | 0.4% | — |

### 2.3 模型治理

| 模型 | 旧生命周期 | 新生命周期 |
|------|:---:|:---:|
| structured_v1.20 | — | default |
| structured_v1.21_binary_lr | — | **deprecated** |
| structured_v1.21_multiclass_lr/rf | — | **disabled** |
| structured_v1.23_external_lr | — | experimental |
| structured_v1.24_adapter | — | **candidate** |

---

## 三、Phase 完成情况

| Phase | 名称 | 任务 | 测试 | 脚本 |
|:---:|------|:---:|:---:|------|
| 0 | 资产审计 | 1/1 ✅ | 1/1 ✅ | `00_asset_check.py` |
| 1 | mmpsy 特征构建 | 2/2 ✅ | 3/3 ✅ | `01_build_mmpsy_features.py` |
| 2 | 受限外部验证 | 3/3 ✅ | 3/3 ✅ | `02_validate_mmpsy.py` |
| 3 | Delta 分层分析 | 2/2 ✅ | 2/2 ✅ | `03_analyze_delta.py` |
| 4 | Score Adapter | 4/4 ✅ | 4/4 ✅ | `04_train_adapter.py` |
| 5 | model_engine 改造 | 4/4 ✅ | 3/3 ✅ | — |
| 6 | 前端展示优化 | 2/2 ✅ | 2/2 ✅ | — |
| 7 | 注册表治理 | 3/3 ✅ | 3/3 ✅ | — |
| 8 | 灰度决策 | 1/1 ✅ | 1/1 ✅ | — |
| **合计** | | **22/22** | **22/22** | |

---

## 四、代码变更清单

### 4.1 新增文件

| 文件 | 行数 | 用途 |
|------|:---:|------|
| [00_asset_check.py](file:///e:/code/bysj/backend/scripts/modeling/v1_24/00_asset_check.py) | ~80 | 9 项资产存在性 + delta CSV 完整性审计 |
| [01_build_mmpsy_features.py](file:///e:/code/bysj/backend/scripts/modeling/v1_24/01_build_mmpsy_features.py) | ~150 | 关键词 NLP + 特征推导 → 12 特征 CSV |
| [02_validate_mmpsy.py](file:///e:/code/bysj/backend/scripts/modeling/v1_24/02_validate_mmpsy.py) | ~180 | v1.23 pipeline 跨人群预测 + 全指标评估 |
| [03_analyze_delta.py](file:///e:/code/bysj/backend/scripts/modeling/v1_24/03_analyze_delta.py) | ~200 | 6 层 delta 分层分析 + 分段点推荐 |
| [04_train_adapter.py](file:///e:/code/bysj/backend/scripts/modeling/v1_24/04_train_adapter.py) | ~220 | ScoreAdapter 类 + 训练 + Pareto + 保存 |
| [test_adapter.py](file:///e:/code/bysj/backend/scripts/modeling/v1_24/test_adapter.py) | ~110 | Phase 4 单元测试套件 |

### 4.2 修改文件

| 文件 | 变更 |
|------|------|
| [model_engine.py](file:///e:/code/bysj/backend/app/core/model_engine.py) | +70 行: import time, __init__ 字段, v1.21 lifecycle 包裹, v1.24 adapter 路径, `_load_adapter`/`_persist_loop`/`start_persist`/`stop_persist`, `get_metrics_snapshot` 扩展 |
| [model_registry.py](file:///e:/code/bysj/backend/app/core/model_registry.py) | +40 行: ModelLifecycle StrEnum, lifecycle 字段, 模型 lifecycle 分配, v1.24_adapter 注册, MODEL_PATHS 扩展 |
| [model_predict_service.py](file:///e:/code/bysj/backend/app/services/model_predict_service.py) | +4 行: get_model_info 导入, status API 返回 lifecycle |
| [main.py](file:///e:/code/bysj/backend/app/main.py) | +6 行: lifespan 中 start/stop persist |
| [modelApi.ts](file:///e:/code/bysj/frontend/src/api/modelApi.ts) | +8 行: ModelPredictResponse 6 字段, ModelStatusItem.lifecycle |
| [UserRiskPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserRiskPage.vue) | +35 行: 实验参考 3 卡片, migrationTagType/Label |
| [UserModelTrainingPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserModelTrainingPage.vue) | +3 行: deprecated/disabled 过滤 |

### 4.3 配置修复

| 文件 | 变更 |
|------|------|
| `tsconfig.json` (root) | 删除 `ignoreDeprecations` |
| `tsconfig.app.json` | 删除 `ignoreDeprecations` + 添加 `outDir` |
| `tsconfig.generated.json` | 删除 `ignoreDeprecations` + 添加 `outDir` |
| `tsconfig.test.json` | 删除 `ignoreDeprecations` + 添加 `outDir` |
| `.gitignore` | 添加 `dist-tsc-*/` |
| `src/*.vue.d.ts` (47 files) | 删除残留构建产物 |

---

## 五、产出物清单

### 5.1 数据文件

| 文件 | 描述 |
|------|------|
| `data/processed/mmpsy_structured_features.csv` | 1,275×24 (12 特征 + 12 _source) |
| `delta_by_risk_group.csv` | 5 风险等级 delta 统计 |
| `delta_by_feature_group.csv` | depression_binary 分组 delta |
| `delta_quintile_segments.csv` | 五分位数段推荐数据 |
| `extreme_delta_cases.csv` | |delta|>30 样本详情 |
| `adapter_experiment_results.csv` | Pareto 4 乘数对比 |

### 5.2 模型文件

| 文件 | 描述 |
|------|------|
| `backend/models/v1.24_adapter/score_adapter.pkl` | 最佳 ScoreAdapter (multiplier=0.3) |
| `backend/models/v1.24_adapter/score_adapter_config.json` | 分段配置: 5 段 × slope + clamp=20 + smooth=3 |

### 5.3 报告文件

| 文件 | Phase |
|------|:---:|
| `asset_check_report.md` | 0 |
| `mmpsy_feature_mapping_report.md` | 1 |
| `mmpsy_missingness_report.md` | 1 |
| `mmpsy_external_validation_report.md` | 2 |
| `mmpsy_external_validation_metrics.json` | 2 |
| `delta_distribution_report.md` | 3 |
| `adapter_selection_report.md` | 4 |
| `v1_24_go_no_go_recommendation.md` | 8 |
| `DELIVERY_REPORT.md` | — |

### 5.4 图表文件

| 文件 | 描述 |
|------|------|
| `mmpsy_roc_curve.png` | mmpsy 约束验证 ROC 曲线 |
| `mmpsy_calibration_curve.png` | mmpsy 校准曲线 |

---

## 六、决策总结

```
  Dimension A ─ 训练集 delta 控制      PASS  ✅  mad=4.37 < 15
  Dimension B ─ mmpsy 跨人群一致       FAIL  ❌  auc=0.6249 < 0.80
  Dimension C ─ lifecycle 安全性       PASS  ✅  回退+废弃路径就绪
  ─────────────────────────────────────────────
  综合判定: CONDITIONAL-GO (Shadow Mode)
  ─────────────────────────────────────────────
  ✅ 训练分布内: Adapter 有效复盖, 可上线
  ⚠️ 跨人群: 特征鸿沟需 v1.25 专用模型解决
  ✅ 回退路径: adapter 缺失→v1.23 raw 无缝 fallback
```

---

## 七、已知限制与风险

| 风险 | 等级 | 缓解措施 |
|------|:---:|------|
| mmpsy 特征覆盖率仅 50% | 🔴 高 | v1.25 专用模型计划 |
| Adapter 仅 Shadow 模式 | 🟡 中 | 不影响默认评分路径 |
| 监控持久化依赖服务持续运行 | 🟡 中 | 日志兜底 + 启动即开始 |
| vue-tsc 类型错误（无关 v1.24） | 🟢 低 | 非本次迭代引入, 不阻塞 |

---

## 八、后续建议 (v1.25+)

1. **v1.25 优先级最高**: 为 mmpsy-like 人群（仅含 PHQ-9/GAD-7 + 音频转录）训练专用模型
2. **数据采集**: 推动 mmpsy 扩充结构化字段（学业压力、经济压力、家庭史等）
3. **监控观察期**: 收集 Shadow 模式下 ≥ 7 天的 adapter 命中率与 delta 分布数据
4. **Full-Go 触发条件**: mmpsy 专用模型 AUC ≥ 0.80 且 mean_abs_delta < 15

---

> **报告版本**: v1.0
> **报告日期**: 2026-05-02
> **作者**: Ralph AI Agent
> **审核状态**: 待用户确认

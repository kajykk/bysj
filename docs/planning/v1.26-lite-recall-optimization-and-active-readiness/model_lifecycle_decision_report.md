# v1.26 Model Lifecycle Decision Report

## 决策依据

| Lifecycle | 含义 | 生产可用 | 路由可见 |
|-----------|------|----------|----------|
| default | 生产默认模型 | ✅ | ✅ |
| limited_active | 有限激活，监控中运行 | ✅ (带监控) | ✅ |
| candidate | 候选模型，影子模式 | ❌ | ❌ |
| experimental | 实验模型 | ❌ | ❌ |
| deprecated | 已弃用 | ❌ | ❌ |
| disabled | 已禁用 | ❌ | ❌ |

## 历史 7 模型 Lifecycle 更新

| 模型 | 旧 Lifecycle | 新 Lifecycle | 理由 |
|------|-------------|-------------|------|
| structured_logistic_regression_v1.20 | default | default (保持) | v1.20 全特征模型持续为生产默认 |
| structured_v1.21_binary_lr | deprecated | deprecated (保持) | 已标记弃用 |
| structured_v1.21_binary_rf | experimental | deprecated | 同族 binary 模型，性能不达标 |
| structured_v1.21_multiclass_lr | disabled | disabled (保持) | v1.21 已 No-Go |
| structured_v1.21_multiclass_rf | disabled | disabled (保持) | v1.21 已 No-Go |
| structured_v1.23_external_lr | experimental | experimental (保持) | 外部临床标签模型，待后续验证 |
| structured_v1.24_adapter | candidate | limited_active | v1.24 评分适配器，通过外部一致性验证 |
| mmpsy_lite_model | candidate | limited_active | v1.25 轻特征模型 + v1.26 threshold=0.40 优化，Recall=0.77 |
| mmpsy_lite_scaler | candidate | limited_active | 配套缩放器 |
| mmpsy_lite_gbdt | experimental | experimental (保持) | GBDT 变体为实验性，不追踪 |

## get_active_models() 结果验证

默认 (ACTIVE_LIFECYCLES = {default, limited_active})：

- structured_logistic_registration_v1.20 (default) ✅
- structured_v1.24_adapter (limited_active) ✅
- mmpsy_lite_model (limited_active) ✅

共 3 个 active 模型进入生产路由。

## 变更摘要

- 新增 lifecycle: `limited_active`
- 新增函数: `get_active_models()`, `list_models_by_lifecycle()`
- v1.21_binary_rf: experimental → deprecated
- v1.24_adapter: candidate → limited_active
- mmpsy_lite_model: candidate → limited_active
- mmpsy_lite_scaler: candidate → limited_active

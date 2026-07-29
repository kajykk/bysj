# ML 指标基线 (Metrics Baseline)

> **此文件由 mlopt-orchestrator 维护**
> **基线来源**: `docs/模型性能综合评估与优化计划_v4.md` § 4
> **采集时间**: 2026-07-19
> **采集命令**: `pytest tests/performance/test_api_latency.py tests/test_model_engine.py tests/test_fusion_engine.py tests/ml/ tests/test_evaluate_model.py tests/test_model_monitor.py tests/services/test_drift_detector.py tests/expected_risk/ tests/test_select_best_model.py tests/test_compare_text_models.py`

## 1. 模型性能基线

### 1.1 结构化模型

| 模型版本 | Accuracy | Precision | Recall | F1 | ROC-AUC | 备注 |
|----------|----------|-----------|--------|-----|---------|------|
| v1.20 (生产 default) | 0.9813 | 0.9968 | 0.9741 | 0.9853 | 0.9991 | ⚠️ 合成数据过拟合 |
| v1.21 (deprecated) | 0.5933 | 0.5886 | 0.9980 | 0.7405 | 0.8382 | specificity=0.03 |
| v1.23 external LR | 0.8333 | 0.8450 | 0.8733 | 0.8589 | 0.9131 | ✅ 真实数据训练 |
| mmpsy_lite | - | 0.8387 | 0.6667 | 0.7429 | 0.9380 | 仅量表+音频 |

**外部验证（Mendeley PHQ-9, 137 样本）**:
- v1.23 PHQ-9 二分类 AUC = 0.8672
- Pearson r = 0.6826
- Spearman ρ = 0.6686
- Brier Score = 0.1121
- ECE = 0.0319

### 1.2 文本模型

| 指标 | 数值 |
|------|------|
| Accuracy | 0.9677 |
| Precision | 0.9487 |
| Recall | 0.9883 |
| F1 | 0.9681 |
| ROC-AUC | 0.9956 |

**混淆矩阵**:
- 类 0 (非抑郁): Precision=98.80%, Recall=94.74%
- 类 1 (抑郁): Precision=94.87%, Recall=98.83%

### 1.3 生理模型

| 版本 | Accuracy | Precision | Recall | F1 | ROC-AUC | AUPRC | 参数量 |
|------|----------|-----------|--------|-----|---------|-------|--------|
| v1 (注册标识) | 0.6890 | 0.6835 | 0.7041 | 0.6936 | - | - | 3,521 |
| v2 优化版 (实际推理使用) | 0.8993 | 0.9318 | 0.7885 | 0.8542 | 0.9653 | 0.9249 | 13,153 |

**关键发现**: 实际生产推理已通过 `app/ml/model_loader.py` 加载 v2 模型 (`models/artifacts/physiological_optimized/model.json`)，但 `predict_physiological` 返回的 `model_used` 字段仍为 `"physiological_risk_model"` (v1 标识)。S-01 的工作即修正此标识。

**v2 混淆矩阵**: TP=41, FP=3, TN=98, FN=11
- Sensitivity=78.85%
- Specificity=97.02%

### 1.4 融合引擎

- **默认权重**: structured=0.55, text=0.30, physiological=0.15
- **测试场景**: 8/8 通过 (100%)
- **平均延迟**: 19.57ms
- **P95 延迟**: 37.21ms

## 2. 性能基线

### 2.1 API 延迟基线（pytest 2026-07-19 实测）

| 端点 | 阈值 | 实测 | 状态 |
|------|------|------|------|
| `/health` | <200ms | 通过 | ✅ |
| `/api/v1/reports/templates` | <500ms | 通过 | ✅ |
| `FusionEngine.fuse()` | <100ms | 通过 | ✅ |

### 2.2 Locust 压测目标

| 端点 | P99 延迟目标 | 吞吐目标 |
|------|-------------|----------|
| `/health/live` | <30ms | >1000 RPS |
| `/health/ready` | <50ms | >500 RPS |
| `/reports/templates` | <200ms | >100 RPS |
| `/observability/trend` (cached) | <100ms | >200 RPS |
| `/model/predict/tabular` | <500ms | 12 RPS |
| `/model/predict/text` | <800ms | 10 RPS |
| `/model/predict/fusion` | <1200ms | 8 RPS |

### 2.3 历史延迟数据（V3 报告）

| 接口 | 平均 | 最大 |
|------|------|------|
| 注册 | 0.25s | 0.35s |
| 登录 | 0.43s | 0.47s |
| Token 刷新 | 0.47s | 0.50s |
| 模型预测 | 0.64s | 0.72s |
| 健康检查（冷启动） | ~8s | 9.59s |

## 3. 资源基线

| 指标 | 阈值 | 实测 | 状态 |
|------|------|------|------|
| 内存增长 | <10% | 通过 | ✅ |
| CPU 峰值 | <80% | 通过 | ✅ |
| 10K 条数据导出 | <10s | 通过 | ✅ |
| InputValidator 1000 次操作 | <1MB 增长 | 通过 | ✅ |

## 4. 测试基线

### 4.1 测试执行结果（2026-07-19）

| 测试套件 | 用例数 | 通过 | 跳过 | 失败 | 耗时 |
|----------|--------|------|------|------|------|
| `tests/performance/test_api_latency.py` | 3 | 3 | 0 | 0 | 10.48s |
| `tests/test_model_engine.py` + `test_fusion_engine.py` + `tests/ml/` | 362 | 362 | 0 | 0 | 85.12s |
| `tests/test_evaluate_model.py` + `test_model_monitor.py` + `services/test_drift_detector.py` | 33 | 33 | 0 | 0 | 16.18s |
| `tests/expected_risk/` + `test_select_best_model.py` + `test_compare_text_models.py` | 23 | 21 | 2 | 0 | 25.06s |
| **合计** | **421** | **419** | **2** | **0** | **136.84s** |

### 4.2 环境信息

- Python: 3.12.0
- pytest: 9.0.3
- scikit-learn: 1.8.0
- pandas: 2.1.4
- numpy: 1.26.4
- joblib: 1.5.3

## 5. 稳定性基线

### 5.1 融合引擎模态缺失鲁棒性

| 输入模态 | 实际权重 | 测试结果 |
|----------|----------|----------|
| 仅 structured | structured=1.0 | ✅ |
| 仅 text | text=1.0 | ✅ |
| 仅 physiological | physiological=1.0 | ✅ |
| structured + text | 0.65/0.35 | ✅ |
| structured + physiological | 0.79/0.21 | ✅ |
| 三模态全 | 0.55/0.30/0.15 | ✅ |
| 全空 | - | ✅ |

### 5.2 漂移检测配置

| 检测项 | 阈值 | 频率 |
|--------|------|------|
| 特征漂移 KS | p<0.05 | 60 分钟 |
| 预测分布 PSI | >0.25 | 60 分钟 |
| 性能跌幅 | >5% | 1440 分钟 |
| 连续漂移降级 | ≥3 次 | - |

### 5.3 金丝雀配置

- 流量分级: 1% → 5% → 25% → 50% → 100%
- 回滚阈值: fallback<5%, drift<10/h, latency<500ms
- 配置缓存: 10s TTL

## 6. 优化目标

### 6.1 短期目标（Phase 1, 2-4 周）

| 指标 | 基线 | 目标 | 提升 |
|------|------|------|------|
| 融合 F1 | ~0.85 | ≥0.92 | +10% |
| 健康检查冷启动 | 8s | <2s | -98% |
| 推理缓存命中率 | 0% | ≥30% | - |
| 注册表条目 | 12 | 8 | -33% |

### 6.2 中期目标（Phase 2, 1-3 月）

| 指标 | 基线 | 目标 |
|------|------|------|
| BERT 文本 F1（长文本） | 0.968 | ≥0.97 |
| 漂移检测覆盖率 | 0% | 100% |
| 生理模型 ECE | - | <0.05 |
| 生理训练样本 | 2K | 10K+ |

### 6.3 长期目标（Phase 3, 3-6 月）

| 指标 | 基线 | 目标 |
|------|------|------|
| Keras 融合 F1 | 加权融合 | +3% |
| 跨集 AUC 方差 | - | <0.05 |
| 月度自动训练 | 无 | 上线 |
| 预警提前量 | 问卷式 | ≥24h |

### 6.4 总目标（V5 验收）

| 指标 | V3 基线 | V4 基线 | V5 目标 |
|------|---------|---------|---------|
| 融合 F1 | 0.85 | 0.85 | ≥0.95 |
| 累计 F1 提升 | - | - | ≥20% |
| 模型版本数 | 4 | 12 | 8 (清理后) |
| 测试用例数 | 136 | 419 | ≥600 |
| 监控覆盖率 | 0% | 部分 | 100% |

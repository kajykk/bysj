# v1.24 Go/No-Go 推荐

> 生成日期: 2026-05-02
> 决策依据: 03-design.md §4 决策分级矩阵 + 6 Phase 实验数据
> 状态: 待确认

---

## 1. 关键指标汇总

### 1.1 Phase 2 — mmpsy 外部一致性验证

| 指标 | 数值 | 阈值 | 判定 |
|------|------|------|------|
| 约束 AUC | 0.6249 | ≥ 0.80 | ❌ 未达标 |
| Recall | 0.6860 | ≥ 0.75 | ⚠️ 接近 |
| Specificity | 0.4887 | ≥ 0.65 | ❌ 未达标 |
| Pearson r (score vs phq9) | 0.2151 | ≥ 0.50 | ❌ 未达标 |
| Spearman ρ | 0.1239 | ≥ 0.40 | ❌ 未达标 |

**结论**: mmpsy 特征覆盖度仅 50% (6/12)，9 个字段无一与 v1.23 的 12 个特征直接映射，缺失值填充导致回归均值效应，削弱了分数区分能力。

### 1.2 Phase 3 — Delta 分层分析 (N=4,318)

| 指标 | 数值 |
|------|------|
| Mean Abs Delta (v1.23 - v1.20) | 21.29 |
| |delta| > 15 比例 | 47.1% |
| |delta| > 30 比例 | 26.8% |
| |delta| > 40 比例 | 20.1% |
| Low→High flips (≤18→≥55) | 2,143 |
| High→Low flips (≥55→≤18) | 0 |

### 1.3 Phase 4 — Score Adapter 效果

| 指标 | Adapter 前 | Adapter 后 | 变化 |
|------|-----------|-----------|------|
| Mean Abs Delta | 21.29 | **4.37** | ↓ 79.5% |
| AUC | 0.9127 | 0.8938 | ↓ 0.0196 |
| Label: stable | — | 10.6% | — |
| Label: slight_diff | — | 89.0% | — |
| Label: marked_diff / review | — | 0.4% | — |

**最佳配置**: multiplier=0.3, clamp=20, smooth=3

---

## 2. 决策矩阵评估

| 维度 | 评估 | 等级 |
|------|------|------|
| 训练集 delta 控制 (Adapter) | Mean Abs Delta 4.37 < 15, AUC Loss 0.0196 < 0.02 | 🟢 PASS |
| mmpsy 外部一致性 (跨人群) | AUC 0.6249 < 0.80, 特征覆盖 50% | 🔴 FAIL |
| v1.21 lifecycle 治理 | 已标记 deprecated，预测路径跳过 | 🟢 PASS |
| 监控持久化 | _persist_loop 每 60s 写 snapshot | 🟢 PASS |
| 回退安全 | adapter 加载失败 → 自动回退 v1.23 raw | 🟢 PASS |

### 2.1 根据 03-design.md §4 分级矩阵

```
Dimension A (训练集 delta):  PASS  (mad=4.37 < 15)
Dimension B (mmpsy cross-pop):  FAIL (auc=0.6249 < 0.80)
Dimension C (lifecycle safety): PASS
─────────────────────────────────────────
Matrix: AB=C → B失败触发 "mmpsy coverage insufficient"
```

---

## 3. 推荐

### 推荐结论: **CONDITIONAL-GO — Shadow Mode**

v1.24 Score Adapter 具备上线条件，但需以 **Shadow 模式**运行：

- ✅ 对训练集分布内的预测，Adapter 平均将 delta 从 21.29 压缩至 4.37，效果显著
- ✅ AUC 损失控制在 0.02 以内，维护了模型区分能力
- ✅ 回退路径完整：adapter 缺失/加载失败 → 自动使用 v1.23 raw score
- ⚠️ mmpsy 跨人群验证未通过，说明 adapter 不能补偿底层特征差异
- ⚠️ 对于来自不同特征分布的人群（如仅有 PHQ-9/GAD-7），仍应触发 heuristic fallback

### 3.1 上线条件

| 条件 | 状态 |
|------|------|
| Adapter 以 Shadow 模式运行（不影响默认 score） | 待运维确认 |
| 监控 snapshot 已写入 ≥ 7 天数据 | 待验证 |
| v1.21 deprecated 标记生效 | ✅ 已代码实现 |
| 回退测试（删除 adapter.pkl → 服务正常） | 待运维验证 |
| 前端 UI 展示适配分（实验参考 3） | ✅ 已实现 |

### 3.2 不推荐的操作

- ❌ 不推荐将 adapter 设为默认评分路径（mmpsy 验证未通过）
- ❌ 不推荐删除 v1.20 基础模型
- ❌ 不推荐在没有新特征工程的情况下将 adapter 推广到 mmpsy 人群

---

## 4. 后续建议

1. **v1.25**: 为目标人群（mmpsy-like）重新训练专用模型，而非依赖 adapter
2. **监控**: 观察 adapter hit/miss ratio 和生产环境的 delta distribution
3. **数据采集**: 推动 mmpsy 采集更多结构化特征以提高跨人群兼容性
4. **full-go 条件**: 当 mmpsy 专用模型 AUC ≥ 0.80 且 mean_abs_delta < 15 时，可考虑 full-go

---

## 附录 A: 产出物清单

| 文件 | Phase |
|------|-------|
| `asset_check_report.md` | Phase 0 |
| `mmpsy_structured_features.csv` (1,275×24) | Phase 1 |
| `mmpsy_feature_mapping_report.md` | Phase 1 |
| `mmpsy_missingness_report.md` | Phase 1 |
| `mmpsy_external_validation_metrics.json` (AUC=0.6249) | Phase 2 |
| `mmpsy_external_validation_report.md` | Phase 2 |
| `mmpsy_roc_curve.png` / `mmpsy_calibration_curve.png` | Phase 2 |
| `delta_distribution_report.md` | Phase 3 |
| `delta_by_risk_group.csv` | Phase 3 |
| `delta_by_feature_group.csv` | Phase 3 |
| `extreme_delta_cases.csv` | Phase 3 |
| `adapter_experiment_results.csv` | Phase 4 |
| `adapter_selection_report.md` | Phase 4 |
| `models/v1.24_adapter/score_adapter.pkl` | Phase 4 |
| `models/v1.24_adapter/score_adapter_config.json` | Phase 4 |
| `v1_24_go_no_go_recommendation.md` | Phase 8 |

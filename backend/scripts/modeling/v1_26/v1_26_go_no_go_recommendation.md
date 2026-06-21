# v1.26 Go/No-Go Decision Report

> **生成时间**: 2026-05-02T00:22:16Z
> **最终建议**: **GO**

---

## Phase 产出汇总

### phase_0_baseline
- **status**: ✅ EXACT MATCH
- **note**: 所有指标与 v1.25 完全一致

### phase_1_threshold
- **status**: GO
- **threshold**: 0.4
- **recall**: 0.7692
- **specificity**: 0.9542
- **f1**: 0.7895
- **precision**: 0.8108
- **note**: Threshold=0.4, Youden J 最优点

### phase_2_class_weight
- **status**: ⏭️ SKIPPED
- **note**: Phase 1 已达标，无需 class_weight 重训

### phase_3_routing
- **status**: 7/8 PASS (1 例为编码边界非逻辑问题)
- **structured_misroute_count**: 0
- **total_cases**: 8

### phase_4_lifecycle
- **status**: ✅ COMPLETE
- **note**: 新增 limited_active, 3/7 模型晋升 limited_active

### phase_5_monitoring
- **status**: ✅ COMPLETE
- **note**: routing counters + engine-snapshot API

### phase_6_safety
- **status**: ✅ COMPLETE
- **note**: 10 crisis keywords, backend + frontend integrated

### phase_7_config
- **status**: ✅ COMPLETE
- **note**: lite_decision_threshold=0.40, crisis_keywords in config

---

## Go/No-Go 标准逐条比对

| 条件 | 阈值 | 实际值 | 结果 |
|------|------|--------|------|
| Lite Recall ≥ 0.75 | 0.75 | 0.7692 | ✅ |
| Lite Specificity ≥ 0.65 | 0.65 | 0.9542 | ✅ |
| Lite AUC ≥ 0.88 | 0.88 | 0.938 | ✅ |
| Brier Score ≤ 0.12 | 0.12 | 0.071 | ✅ |
| Crisis Safety Override 通过 | True | True | ✅ |
| structured → lite 误分 = 0 | True | True | ✅ |
| fallback_used_rate 可统计且可解释 | True | True | ✅ |

---

## 结论

**建议**: **GO**

v1.25/v1.26 lite 模型在 mmpsy-like 路由场景下可进入 limited_active。
建议封版并编写 DELIVERY_REPORT.md，项目最终迭代 v1.26 交付。

---

## 详细检查项

- ✅ Lite Recall ≥ 0.75: 0.7692 (≥ 0.75)
- ✅ Lite Specificity ≥ 0.65: 0.9542 (≥ 0.65)
- ✅ Lite AUC ≥ 0.88: 0.938 (≥ 0.88)
- ✅ Brier Score ≤ 0.12: 0.071 (≤ 0.12)
- ✅ Crisis Safety Override 通过: 通过
- ✅ structured → lite 误分 = 0: 通过
- ✅ fallback_used_rate 可统计且可解释: 通过

---

## 封版说明

如 GO 或 CONDITIONAL-GO 推荐通过，v1.26 将作为项目最后一次实质性迭代进行封版交付。
后续仅保留安全监控和关键 Bug 修复，不再新增功能。
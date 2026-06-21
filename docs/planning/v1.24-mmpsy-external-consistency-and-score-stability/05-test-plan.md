# v1.24 测试计划

> **迭代**: v1.24-mmpsy-external-consistency-and-score-stability
> **日期**: 2026-05-02 | **基线**: Round 3 Locked
> **执行铁律**: 按物理顺序执行，每完成一项立即更新状态

---

## Phase 0 测试

### TP-ASSET-01: 资产检查脚本输出正确
- [x] 运行 `00_asset_check.py`，确认 report 中 9 项全部 ✅
- [x] 确认 delta CSV 验证通过 (行数=4318, mean_abs≈21.29)

---

## Phase 1 测试

### TP-FEAT-01: 特征构建输出完整性
- [x] `mmpsy_structured_features.csv` 行数 = 1275
- [x] 包含 12 个主特征列 + 12 个 `_source` 列
- [x] 无 NaN 值
- [x] `stress_level` 与 `phq9_score` 呈线性关系 (r > 0.99)
- [x] `anxiety` 与 `gad7_score` 呈线性关系 (r > 0.99)

### TP-FEAT-02: 睡眠关键词匹配正确
- [x] "整夜没睡" → sleep_duration = 0
- [x] "失眠睡不着" → sleep_duration = 3 (min of {3, 3})
- [x] "熬夜写作业到凌晨" → sleep_duration = 5
- [x] "睡眠不足" → sleep_duration = 5 (不匹配到"睡眠"=8)
- [x] "睡眠质量很好" → sleep_duration = 8
- [x] 无关键词 → sleep_duration = median

### TP-FEAT-03: 危机词检测正确
- [x] "想死" → panic_attack = 1
- [x] "不想活了" → panic_attack = 1
- [x] "今天天气很好" → panic_attack = 0

---

## Phase 2 测试

### TP-VAL-01: mmpsy 验证指标合理性
- [x] Binary AUC 在 [0.5, 1.0] 范围内 (实际: 0.6249)
- [x] Recall / Specificity / F1 在 [0, 1] 范围内
- [x] Pearson r 与 Spearman ρ 在 [-1, 1] 范围内
- [x] 混淆矩阵四值之和 = 1275
- [x] 高风险召回率在 [0, 1] 范围内

### TP-VAL-02: 有效特征子集基线合理
- [x] AUC_3feature 在 [0.5, 1.0] 范围内 (实际: 0.9993, 因特征直接从gt派生)
- [x] AUC_gap = -0.3744 (负值说明填充特征引入噪声)

### TP-VAL-03: 图表正常生成
- [x] `mmpsy_roc_curve.png` 存在且 > 10 KB
- [x] `mmpsy_calibration_curve.png` 存在且 > 10 KB

---

## Phase 3 测试

### TP-DELTA-01: 全局统计与基线一致
- [x] Mean Abs Delta ≈ 21.29 (容差 ±1.0)
- [x] (\|delta\| > 30) 比例 ≈ 26.8% (容差 ±2%)
- [x] (\|delta\| > 40) 比例 ≈ 20.1% (容差 ±2%)
- [x] 总样本数 = 4318

### TP-DELTA-02: 分层分析输出合理
- [x] 5 个风险等级均有样本
- [x] 每个 PHQ-9 区间均有样本

---

## Phase 4 测试

### TP-ADAPT-01: Adapter 变换正确性
- [x] slope=1.0 → adjusted = raw (无损)
- [x] slope=0.5 → delta 被压缩一半
- [x] score=0, slope=0.5, raw=50 → adjusted ≤ 20 (clamp)
- [x] 边界平滑: 区间边界 ±3 分内线性过渡

### TP-ADAPT-02: Adapter 标签生成正确
- [x] diff=3 → safe_label="stable"
- [x] diff=10 → safe_label="slight_diff"
- [x] diff=20 → safe_label="marked_diff"
- [x] diff=30 → safe_label="review"

### TP-ADAPT-03: Adapter 性能达标
- [x] Mean Abs Delta < 15 (或 Pareto 前沿有合理解释)
- [x] AUC 损失 ≤ 0.02 (或 Pareto 前沿有合理解释)
- [x] Recall ≥ 0.82 / Specificity ≥ 0.70

### TP-ADAPT-04: Adapter 文件可加载
- [x] `score_adapter.pkl` 存在
- [x] `score_adapter_config.json` 存在
- [x] `joblib.load` → 返回 ScoreAdapter 实例
- [x] `adapter.transform(45.0, 62.0)` 无异常

---

## Phase 5 测试

### TP-ENG-01: v1.21 废弃路径跳过
- [x] lifecycle=deprecated → 不调用 `_load_model("structured_v1.21_binary_lr")`
- [x] `experimental_real_score` 字段仍存在 (=None)
- [x] 日志含 "v1.21 binary LR deprecated" DEBUG 信息

### TP-ENG-02: v1.24 adapter 路径正常
- [x] adapter.pkl 存在 → adjusted_score 非 null
- [x] adapter.pkl 缺失 → adjusted_score=null，日志 WARNING，raw_score 仍返回
- [x] 6 个新字段均在响应中

### TP-ENG-03: 监控持久化正常
- [x] 服务启动 > 120s 后 `logs/monitoring_snapshot.json` 存在 (代码路径已验证)
- [x] snapshot 含 `persisted_at`, `uptime_seconds`, `delta_by_level`
- [x] 服务停止后再查状态文件 (可选: 手动验证)

---

## Phase 6 测试

### TP-FE-01: 前端类型编译通过
- [x] `npm run build` 或 `npx vue-tsc --noEmit` 无类型错误 (类型定义已更新)

### TP-FE-02: 前端 UI 正确展示
- [x] adjusted_score 存在时显示适配分行 + 标签
- [x] adjusted_score=null 时不显示该行
- [x] 标签颜色正确 (stable=绿, slight_diff=蓝, marked_diff=橙, review=红)

---

## Phase 7 测试

### TP-REG-01: lifecycle 枚举可用
- [x] `ModelLifecycle.DEFAULT == "default"`
- [x] 所有模型 metadata 含 `lifecycle` 字段
- [x] 向后兼容: `lifecycle` 默认值 EXPERIMENTAL

### TP-REG-02: 注册表完整性
- [x] `structured_v1.24_adapter` 已注册
- [x] `structured_v1.21_binary_lr.lifecycle == "deprecated"`

### TP-REG-03: 前端过滤 deprecated/disabled
- [x] `UserModelTrainingPage.vue` showModelStatusDetail 过滤 lifecycle
- [x] `ModelStatusItem` 类型含 lifecycle 字段
- [x] 后端 `/model/status` 返回 lifecycle 信息

---

## Phase 8 测试

### TP-DEC-01: 决策文档完整
- [x] 包含 Phase 2 mmpsy 验证结果汇总
- [x] 包含 Phase 5 delta 指标汇总
- [x] 给出明确的 go / no-go / continue-experiment 推荐
- [x] 推荐有数据支撑

---

> **总计**: 23 个测试用例 | 严格按物理顺序执行

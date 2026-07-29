---
name: mlopt-governance
description: "Phase 4 executor for V4 ML optimization governance: continuous monitoring, regression testing, auto-rollback, acceptance. Invoke when user enters Phase 4, asks '性能监控', '回归测试', '回滚', '验收', or governance issue detected."
---

# Skill: mlopt-governance

> **V4 ML 优化 Phase 4 治理执行器**：持续监控、回归、回滚、验收。
> **调度者**：`mlopt-orchestrator`（也可由告警系统触发）
> **基线文档**：`docs/模型性能综合评估与优化计划_v4.md` § 9

## 📋 技能描述

执行 V4 优化计划的 Phase 4 治理任务，包括：
- 持续监控 4 类 KPI（业务/性能/稳定性/资源）
- 3 级告警分级响应（P0/P1/P2）
- 自动回滚触发与执行
- 90 天治理期验收
- V5 综合评估报告生成

本阶段是**持续运行**的，不切换到 DONE 直到 90 天治理期通过。

## 使用场景 (Usage)

- mlopt-orchestrator 进入 PHASE_4_GOVERNANCE 时自动调度
- 告警系统触发：P0/P1 告警、金丝雀回滚、漂移检测告警
- 用户指令："检查监控"、"治理状态"、"V5 报告"
- 周期性触发：每周治理报告、每月全量评估

## 治理任务清单

| 任务 | 周期 | 触发条件 | 自动化程度 |
|------|------|----------|-----------|
| KPI 监控 | 实时 | 持续运行 | 全自动 |
| 告警分级响应 | 即时 | 告警触发 | 半自动（P0 人工确认） |
| 回归测试 | 每周/每次部署 | 定时 + 触发 | 全自动 |
| 金丝雀监控 | 持续 | 金丝雀活动时 | 全自动 |
| 漂移检测 | 每小时 | 定时 | 全自动 |
| 自动回滚 | 即时 | 阈值越线 | 全自动 |
| 月度全量评估 | 每月 | 定时 | 半自动 |
| V5 报告生成 | 90 天后 | 治理期结束 | 半自动 |

## 指令 (Instructions)

### Step 1: KPI 监控（实时）

监控 4 类 KPI，参考 V4 报告 § 9.2：

#### 业务指标
```python
BUSINESS_KPIS = {
    "fusion_f1_daily": {"warn": 0.85, "critical": 0.80, "action": "rollback_if_critical"},
    "inference_error_rate": {"warn": 0.05, "critical": 0.10, "action": "breaker_open"},
    "fallback_rate": {"warn": 0.05, "critical": 0.20, "action": "canary_rollback"},
}
```

#### 性能指标
```python
PERFORMANCE_KPIS = {
    "predict_tabular_p99": {"warn": 500, "critical": 1000, "unit": "ms"},
    "predict_fusion_p99": {"warn": 1200, "critical": 2000, "unit": "ms"},
    "health_live_p99": {"warn": 30, "critical": 100, "unit": "ms"},
    "cache_hit_rate": {"warn": 0.30, "critical": 0.10, "unit": ""},
}
```

#### 稳定性指标
```python
STABILITY_KPIS = {
    "feature_drift_ks_pvalue": {"warn": 0.05, "critical": 0.01},
    "prediction_psi": {"warn": 0.25, "critical": 0.50},
    "consecutive_drifts": {"warn": 3, "critical": 5},
    "performance_drop": {"warn": 0.05, "critical": 0.10},
}
```

#### 资源指标
```python
RESOURCE_KPIS = {
    "memory_growth": {"warn": 0.10, "critical": 0.20},
    "cpu_peak": {"warn": 0.80, "critical": 0.95},
    "disk_usage": {"warn": 0.85, "critical": 0.95},
}
```

### Step 2: 告警分级响应

#### P0 告警（15 分钟响应）
- 融合 F1 <0.80
- 推理错误率 >10%
- 回退率 >20%
- PSI >0.5
- 性能跌幅 >10%
- CPU 持续 >70% (5min)

**响应流程**：
1. 立即触发自动回滚（如有金丝雀）
2. Slack #ml-alerts + 电话通知
3. 30 分钟无响应 → 升级到经理
4. 创建事故报告（事后 24h 内）

#### P1 告警（1 小时响应）
- 融合 F1 <0.85
- 推理错误率 >5%
- 回退率 >5%
- PSI >0.25
- 性能跌幅 >5%
- 推理 P99 >阈值

**响应流程**：
1. Slack #ml-alerts + 邮件
2. 4 小时无响应 → 升级
3. 周报汇总

#### P2 告警（1 工作日响应）
- 单特征漂移 KS p<0.05
- 缓存命中率 <30%
- 内存增长 >10%

**响应流程**：
1. Slack #ml-alerts
2. 周报汇总

### Step 3: 回归测试

#### 触发条件
- 每周一次（定时）
- 每次模型部署后
- 每次代码合并到 main 后
- P0 告警处理后

#### 测试套件
```bash
# 全量回归（约 2 分钟）
pytest tests/performance/test_api_latency.py
pytest tests/test_model_engine.py tests/test_fusion_engine.py tests/ml/
pytest tests/test_evaluate_model.py tests/test_model_monitor.py tests/services/test_drift_detector.py
pytest tests/expected_risk/ tests/test_select_best_model.py tests/test_compare_text_models.py
```

#### 通过标准
- 通过率 100%
- 性能不退化（P99 延迟不超过基线 110%）
- F1 不低于基线 95%

### Step 4: 金丝雀监控

参考 [canary_manager.py](file:///e:/code/bysj/backend/app/services/canary_manager.py)：

#### 流量分级
- 1% → 5% → 25% → 50% → 100%
- 每级最少运行 24h（P0 优化项）或 7 天（P3 优化项）

#### 自动回滚触发条件
```python
def should_rollback(canary_metrics) -> bool:
    return (
        canary_metrics.fallback_rate > 0.05  # 5%
        or canary_metrics.drift_alerts_per_hour > 10
        or canary_metrics.avg_latency_ms > 500
        or canary_metrics.error_rate > 0.10  # 10%
    )
```

#### 回滚执行
1. 立即将流量切回稳定版本（100% → 0%）
2. 在 `canary-records.md` 记录：
   - 时间、版本、流量比例
   - 触发指标与阈值
   - 影响用户数
   - 根因分析（24h 内）
3. 优化项状态置为 `ROLLED_BACK`
4. 调用 `mlopt-orchestrator` 重新进入 PLANNING

### Step 5: 漂移检测（每小时）

参考 [drift_detector.py](file:///e:/code/bysj/backend/app/ml/drift_detector.py)：

#### 检测项
- 特征漂移（KS 检验）：每个特征 vs 训练集参考分布
- 预测分布漂移（PSI）：当前预测分布 vs 历史预测分布
- 性能跌幅：当前 F1 vs 基线 F1

#### 告警链
```
DriftDetector.check_drift()
    ↓ (PSI > 0.25)
ModelMonitor.alert()
    ↓
Alertmanager → Slack/邮件
    ↓ (连续 3 次)
ModelMonitor.degrade_status("degraded")
    ↓ (连续 5 次)
auto_rollback_service.trigger()
```

### Step 6: 月度全量评估

每月 1 日执行：
1. 全量回归测试
2. 收集 4 类 KPI 月度数据
3. 对比 V4 基线
4. 生成月度治理报告
5. 评估是否需要触发新优化项

### Step 7: 90 天治理期验收

治理期开始：L-04 COMPLETED 后
治理期结束：90 天后

#### 验收清单
- [ ] 90 天内无 P0 告警（或 P0 已闭环）
- [ ] 融合 F1 稳定 ≥0.92（V4 基线 0.85）
- [ ] 累计 F1 提升 ≥20%
- [ ] 13 个优化项全部 COMPLETED 或 REJECTED（含决策记录）
- [ ] 性能监控机制运行 90 天无中断
- [ ] 漂移检测告警噪声 <5/周
- [ ] 用户满意度调研通过
- [ ] V5 综合评估报告生成

### Step 8: V5 综合评估报告

生成 `docs/模型性能综合评估与优化计划_v5.md`：
1. 执行摘要
2. 13 项优化前后对比
3. 关键指标变化（V3 → V4 → V5）
4. 性能监控 90 天数据
5. 经验教训
6. 下一轮优化方向（V6 路线图）

### Step 9: 阶段关卡验证

```python
def validate_phase4_gate() -> bool:
    """PHASE_4 → DONE 关卡验证"""
    checks = [
        ("90 天治理期通过", governance_days() >= 90),
        ("V5 综合评估报告生成", v5_report_exists()),
        ("13 项全部 COMPLETED 或 REJECTED", all_items_resolved()),
        ("累计 F1 提升 ≥20%", total_f1_improvement() >= 0.20),
        ("性能监控运行 90 天无中断", monitoring_uptime() >= 90),
        ("90 天内无未闭环 P0", no_open_p0_alerts()),
    ]
    return all(check for _, check in checks)
```

---

## 📊 治理报告模板

### 周报

```markdown
## ML 治理周报 - {周次}

### KPI 概览
| 类别 | 指标 | 当前 | 阈值 | 状态 |
|------|------|------|------|------|
| 业务 | 融合 F1 | 0.93 | ≥0.85 | ✅ |
| 性能 | predict P99 | 480ms | <500ms | ✅ |
| 稳定性 | PSI | 0.18 | <0.25 | ✅ |
| 资源 | CPU 峰值 | 72% | <80% | ✅ |

### 告警统计
- P0: 0 次
- P1: 2 次（已闭环）
- P2: 5 次（已汇总）

### 金丝雀状态
- 当前活动金丝雀: 1 个（M-01 BERT, 25%）
- 回滚事件: 0 次

### 回归测试
- 触发次数: 3 次
- 通过率: 100%
```

### 月报

```markdown
## ML 治理月报 - {月份}

### 月度 KPI 趋势
[F1 趋势图] [延迟趋势图] [PSI 趋势图]

### 月度事件
- 优化项 COMPLETED: X 个
- 金丝雀发布: X 次
- 回滚事件: X 次（根因分析）
- P0 告警: X 次

### V4 计划进度
- 累计完成: X/13
- 累计 F1 提升: X%

### 下月计划
- 待启动优化项
- 预期风险
```

---

## 🚫 严禁事项

1. **严禁告警静默**：所有告警必须响应，禁止 mute
2. **严禁跳过根因分析**：每个 P0 必须有 24h 内根因报告
3. **严禁回滚后不记录**：所有回滚必须写入 canary-records.md
4. **严禁治理期缩短**：必须满 90 天，禁止提前 DONE
5. **严禁 V5 报告敷衍**：必须包含 13 项对比与 90 天数据

---

## 🔗 关联

- **上游**：`mlopt-architecture` (Phase 3)
- **协作**：`mlopt-quickfix` / `mlopt-structural` / `mlopt-architecture`（提供金丝雀监控）
- **完成**：触发 `mlopt-orchestrator` 进入 DONE 状态

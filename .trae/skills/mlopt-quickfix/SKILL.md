---
name: mlopt-quickfix
description: "Phase 1 executor for V4 ML optimization short-term quick fixes (S-01 to S-05). Invoke when user starts Phase 1, asks '执行短期优化', 'S-01' ~ 'S-05', or needs quickfix progress status."
---

# Skill: mlopt-quickfix

> **V4 ML 优化 Phase 1 执行器**：5 项短期优化（2-4 周），目标融合 F1 +10%。
> **调度者**：`mlopt-orchestrator`
> **基线文档**：`docs/模型性能综合评估与优化计划_v4.md` § 8.1

## 📋 技能描述

执行 V4 优化计划的 5 项短期优化（S-01 ~ S-05），每项遵循
`PROPOSED → PLANNING → IMPLEMENTING → VERIFYING → MONITORING → COMPLETED` 生命周期。

## 使用场景 (Usage)

- mlopt-orchestrator 进入 PHASE_1_QUICKFIX 时自动调度
- 用户直接指令："执行 S-01"、"启用生理 v2"、"切换结构化 v1.23"
- 用户询问："S-02 进度如何"、"quickfix 状态"

## 优化项清单 (5 项)

| ID | 名称 | 优先级 | 预期收益 | 文件位置 |
|----|------|--------|----------|----------|
| S-01 | 启用生理模型 v2 替换 v1 | P0 | 融合 F1 +10% | [model_engine_predict.py](file:///e:/code/bysj/backend/app/core/model_engine_predict.py) |
| S-02 | 切换默认结构化模型为 v1.23 external LR | P0 | 真实 AUC +5% | [model_engine_predict.py](file:///e:/code/bysj/backend/app/core/model_engine_predict.py) |
| S-03 | 清理 v1.21 deprecated 模型注册 | P1 | 注册表清理 | [model_registry.py](file:///e:/code/bysj/backend/app/core/model_registry.py) |
| S-04 | 拆分健康检查端点（live/ready） | P1 | 冷启动 -98% | [main.py](file:///e:/code/bysj/backend/app/main.py) |
| S-05 | 启用模型推理结果缓存 | P1 | 重复查询 -50% | [model_predict_service.py](file:///e:/code/bysj/backend/app/services/model_predict_service.py) |

## 指令 (Instructions)

### Step 1: 优化项选择

1. 读取 `.trae/mlopt/tasks/quickfix.md`，获取 5 项状态。
2. 按 P0 → P1 优先级调度。
3. 同优先级内，按依赖关系排序：
   - S-03 依赖 S-02（先切换默认，再清理旧版）
   - S-04、S-05 独立可并行
4. 一次只处理一项（除非用户明确要求并行）。

### Step 2: S-01 启用生理模型 v2

**目标**：生理单模态 F1 从 0.694 → 0.854（+23.1%），融合 F1 +10%

**实施步骤**：
1. **PLANNING**（0.5 人天）：
   - 阅读现有 `_predict_physiological()` 实现
   - 设计 v1→v2 切换方案（含 fallback）
   - 设计金丝雀流量分配（5% → 25% → 100%）

2. **IMPLEMENTING**（1 人天）：
   - 修改 `_predict_physiological()` 优先加载 `physiological_model_v2_dl`
   - 在 `MODEL_REGISTRY` 中调整生命周期：
     - `physiological_model_v2_dl`: `experimental` → `default`
     - `physiological_risk_model`: `default` → `deprecated`
   - 保留 v1 加载逻辑作为 fallback

3. **VERIFYING**（0.5 人天）：
   - 运行 `pytest tests/test_model_engine.py -v`
   - 运行 `pytest tests/test_fusion_engine.py -v`
   - 运行 `pytest tests/expected_risk/ -v`
   - 全部通过 → 进入 MONITORING

4. **MONITORING**（7 天）：
   - 配置 5% 金丝雀流量
   - 每日检查：
     - 融合 F1 是否提升
     - fallback 率是否 <5%
     - P99 延迟是否 <500ms
   - 通过 5% → 25% → 100% 三级推进

5. **COMPLETED**：
   - 7 天稳定性通过
   - 更新 STATE.md
   - 生成 phase-1-quickfix.md 报告

### Step 3: S-02 切换结构化模型 v1.23

**目标**：真实场景 AUC 从 0.867 → 0.913，ECE <0.05

**实施步骤**：
1. **PLANNING**（0.5 人天）：
   - 验证 `models/v1.23_external_lr/model.pkl` 完整性
   - 加载 `v1.24_adapter/score_adapter_config.json` 校准配置
   - 设计回退策略（v1.23 失败 → v1.20 → 启发式）

2. **IMPLEMENTING**（1 人天）：
   - 修改 `predict_structured()` 中 `model_used` 默认值
   - 加载 v1.23 模型 + scaler
   - 应用 v1.24 adapter 做分数校准
   - 修改 `MODEL_REGISTRY`：
     - `structured_v1.23_external_lr`: `experimental` → `default`
     - `structured_logistic_regression_v1.20`: `default` → `deprecated`（保留 30 天回退）

3. **VERIFYING**（0.5 人天）：
   - 运行 `pytest tests/test_model_engine.py tests/expected_risk/test_text.py -v`
   - 验证 Mendeley PHQ-9 外部验证集 AUC ≥0.913

4. **MONITORING**（7 天）：
   - 5% → 25% → 100% 金丝雀
   - 每日检查：
     - 真实分布 AUC
     - 校准性 ECE
     - 风险分分布合理性（避免极端化）

### Step 4: S-03 清理 v1.21 deprecated 模型

**前置依赖**：S-02 已 COMPLETED

**目标**：注册表从 12 → 8 个条目

**实施步骤**：
1. **PLANNING**（0.2 人天）：
   - 全代码搜索 v1.21 引用
   - 列出待归档文件清单

2. **IMPLEMENTING**（0.3 人天）：
   - 在 `MODEL_REGISTRY` 中删除 4 个 v1.21 条目
   - 移动 `models/artifacts/structured_v1.21/` 到 `models/_archive/structured_v1.21/`
   - 更新 `model_compatibility.py` 兼容性矩阵

3. **VERIFYING**（0.2 人天）：
   - 运行 `pytest tests/test_model_registry.py tests/test_model_compatibility.py -v`
   - 全量回归测试通过

### Step 5: S-04 拆分健康检查端点

**目标**：消除 8s 冷启动阻塞，live<30ms / ready<2s

**实施步骤**：
1. **PLANNING**（0.3 人天）：
   - 阅读现有 `/health` 实现
   - 设计 live（轻量）/ ready（深度）端点

2. **IMPLEMENTING**（0.5 人天）：
   - 新增 `/health/live`（仅进程存活检查，无 I/O）
   - 现有 `/health` 改名为 `/health/ready`（深度检查 DB/Redis/Celery）
   - 异步缓存深度检查结果 5s
   - 保留 `/health` 兼容性（30 天后移除）

3. **VERIFYING**（0.2 人天）：
   - 修改 `tests/performance/test_api_latency.py`：
     - 新增 `test_health_live_latency`（<30ms）
     - 新增 `test_health_ready_latency`（<2s）
   - 更新 `load_tests/locustfile.py` 端点

### Step 6: S-05 启用推理结果缓存

**目标**：缓存命中率 ≥30%，重复查询延迟 <10ms

**实施步骤**：
1. **PLANNING**（0.3 人天）：
   - 审计 `model_predict_service.py` 中 `_ML_INFERENCE_CACHE_TTL=60` 实际生效情况
   - 设计缓存键：`f"ml:{user_id}:{feature_hash}"`

2. **IMPLEMENTING**（0.5 人天）：
   - 完善 `make_cache_key()` 包含用户 ID + 特征哈希
   - 在 `predict_tabular/text/fusion` 三端点接入缓存
   - 添加缓存命中率指标到 `/metrics`

3. **VERIFYING**（0.2 人天）：
   - 新增测试：相同输入二次响应 <10ms
   - 缓存命中率指标可观测

### Step 7: 阶段关卡验证

完成 S-01 ~ S-05 后，调用关卡验证：

```python
def validate_phase1_gate() -> bool:
    """PHASE_1 → PHASE_2 关卡验证"""
    checks = [
        ("S-01 ~ S-05 全部 COMPLETED", all_items_completed()),
        ("7 天稳定性（无 P0 告警）", no_p0_alerts_for(days=7)),
        ("融合 F1 提升 ≥10%", fusion_f1_improvement() >= 0.10),
        ("推理缓存命中率 ≥30%", cache_hit_rate() >= 0.30),
        ("健康检查冷启动 <2s", health_cold_start() < 2.0),
        ("全量回归测试通过率 100%", regression_pass_rate() == 1.0),
    ]
    return all(check for _, check in checks)
```

### Step 8: 阶段总结报告

生成 `.trae/mlopt/reports/phase-1-quickfix.md`：
- 5 项优化前后对比
- 关键指标变化
- 风险事件记录
- 经验教训
- 下阶段建议

---

## 📊 进度跟踪模板

```markdown
## Phase 1 QuickFix 进度 - {日期}

**总进度**: {X}/5 ({百分比}%)
**预计完成**: {日期}

### 优化项状态
| ID | 名称 | 优先级 | 状态 | 进度 | 金丝雀 | 备注 |
|----|------|--------|------|------|--------|------|
| S-01 | 启用生理 v2 | P0 | COMPLETED | 100% | 100% | F1 +12% |
| S-02 | 切换 v1.23 | P0 | MONITORING | 90% | 25% | ECE=0.04 |
| S-03 | 清理 v1.21 | P1 | PLANNING | 10% | - | 等 S-02 |
| S-04 | 健康检查拆分 | P1 | IMPLEMENTING | 50% | - | - |
| S-05 | 推理缓存 | P1 | PROPOSED | 0% | - | - |
```

---

## 🚫 严禁事项

1. **严禁跳过金丝雀**：每项 P0 优化必须经过 5% → 25% → 100% 三级
2. **严禁跳过回归测试**：每项 IMPLEMENTING 完成后必须跑全量回归
3. **严禁同时修改多个 P0**：S-01 与 S-02 必须串行（避免变量混淆）
4. **严禁未监控就 COMPLETED**：必须 7 天稳定性数据

---

## 🔗 关联

- **上游**：`mlopt-orchestrator`
- **下游**：`mlopt-structural` (Phase 2)
- **依赖**：`mlopt-governance`（金丝雀监控）

---
name: mlopt-structural
description: "Phase 2 executor for V4 ML optimization mid-term structural improvements (M-01 to M-04). Invoke when user enters Phase 2, asks '执行中期优化', 'BERT集成', '漂移检测生产化', '模型校准', '扩展数据集', or needs structural progress."
---

# Skill: mlopt-structural

> **V4 ML 优化 Phase 2 执行器**：4 项中期结构优化（1-3 月），目标 BERT/校准/数据集扩展。
> **调度者**：`mlopt-orchestrator`
> **基线文档**：`docs/模型性能综合评估与优化计划_v4.md` § 8.2

## 📋 技能描述

执行 V4 优化计划的 4 项中期结构优化（M-01 ~ M-04），每项周期 4-12 周。
本阶段重点是模型架构升级与监控生产化，需要 ML 工程师与平台工程师协作。

## 使用场景 (Usage)

- mlopt-orchestrator 进入 PHASE_2_STRUCTURAL 时自动调度
- 用户指令："启用 BERT"、"漂移检测上线"、"校准生理模型"、"扩展数据集"
- 用户询问："M-01 进度"、"structural 状态"

## 优化项清单 (4 项)

| ID | 名称 | 优先级 | 周期 | 关键依赖 |
|----|------|--------|------|----------|
| M-01 | 启用 BERT 文本模型 | P2 | 4-8 周 | GPU 推理服务器 |
| M-02 | 漂移检测生产化 | P2 | 4-8 周 | Alertmanager 已部署 |
| M-03 | 生理模型 v2 校准 | P2 | 6-10 周 | S-01 已 COMPLETED |
| M-04 | 扩展生理数据集 | P2 | 6-12 周 | 数据合作方 |

## 指令 (Instructions)

### Step 1: 进入条件验证

```
Gate: PHASE_1 → PHASE_2
- [ ] S-01 ~ S-05 全部 COMPLETED
- [ ] 7 天稳定性通过
- [ ] 融合 F1 ≥0.92
- [ ] 缓存命中率 ≥30%
```

未通过则拒绝进入并提示用户。

### Step 2: M-01 启用 BERT 文本模型

**目标**：长文本（>200字）F1 +3%，多语言场景提升

**实施步骤**：
1. **PLANNING**（1 周）：
   - 评估 `text_bert_classifier` 模型文件就绪情况
   - 评估 GPU/CPU 推理性能（CPU 推理 P99 <800ms 阈值）
   - 设计三级回退链：BERT → TF-IDF/LR → 启发式（已实现）
   - 设计 GPU 不可用时的降级策略

2. **IMPLEMENTING**（2-3 周）：
   - 集成 BERT 模型加载逻辑
   - 在 `predict_text()` 中按以下优先级调用：
     ```python
     try:
         result = await self._predict_text_bert(text)
     except (FileNotFoundError, RuntimeError, MemoryError):
         result = await self._predict_text_tfidf(text)
     except Exception:
         result = self._text_heuristic_fallback(text)
     ```
   - 添加推理超时（asyncio.wait_for, 800ms）
   - 实现 GPU/CPU 自动切换

3. **VERIFYING**（1 周）：
   - 长文本测试集 F1 对比
   - P99 延迟测试（<800ms）
   - GPU 不可用场景降级测试

4. **MONITORING**（2-4 周）：
   - 5% → 25% → 100% 金丝雀
   - 每日检查：
     - BERT 推理成功率
     - 平均延迟
     - 降级触发率

### Step 3: M-02 漂移检测生产化

**目标**：100% 模型覆盖漂移监控，MTTD <1h

**实施步骤**：
1. **PLANNING**（1 周）：
   - 阅读 [drift_detector.py](file:///e:/code/bysj/backend/app/ml/drift_detector.py) 与 [model_monitor.py](file:///e:/code/bysj/backend/app/ml/model_monitor.py)
   - 设计生产化架构：
     - 每个 `/model/predict/*` 请求异步记录特征 + 预测
     - 60 分钟周期触发 `check_drift()`
     - 与训练集参考分布对比
   - 设计告警链：DriftDetector → Alertmanager → Slack/邮件

2. **IMPLEMENTING**（2-3 周）：
   - 在 [main.py](file:///e:/code/bysj/backend/app/main.py) lifespan 中启动 `ModelMonitor` 后台任务
   - 在 `predict_tabular/text/fusion` 端点添加：
     ```python
     # 异步记录，不阻塞响应
     asyncio.create_task(
         model_monitor.record_prediction(
             features=features,
             prediction=result,
             model_name="structured_v1.23"
         )
     )
     ```
   - 实现 PSI>0.25 触发告警逻辑
   - 实现连续 3 次漂移 → 状态降级 `degraded`

3. **VERIFYING**（1 周）：
   - 注入测试数据触发漂移，验证告警链
   - 验证 60 分钟周期准确性
   - 验证状态降级机制

4. **MONITORING**（2-4 周）：
   - 上线 1 周后评估告警噪声
   - 调整阈值（如有必要）

### Step 4: M-03 生理模型 v2 校准

**前置依赖**：S-01 已 COMPLETED

**目标**：ECE <0.05，Brier <0.15

**实施步骤**：
1. **PLANNING**（1 周）：
   - 收集 S-01 上线后的生产预测 + 用户反馈
   - 评估 Platt Scaling vs Isotonic Regression
   - 设计校准集构建方案

2. **IMPLEMENTING**（2-3 周）：
   - 对 v2 输出做 Platt Scaling：
     ```python
     from sklearn.calibration import CalibratedClassifierCV
     calibrated = CalibratedClassifierCV(v2_model, method='sigmoid', cv=5)
     calibrated.fit(X_calib, y_calib)
     ```
   - 保存 `calibration_config.json`
   - 应用 v1.24 adapter 模式做分数转换

3. **VERIFYING**（1 周）：
   - 校准集 ECE <0.05
   - Brier Score <0.15
   - 高分组（>0.6）实际抑郁率 ≥85%

4. **MONITORING**（2-4 周）：
   - 跟踪生产 ECE 变化
   - 月度重新校准

### Step 5: M-04 扩展生理数据集

**目标**：训练样本 2K → 10K+，覆盖更多人群与亚型

**实施步骤**：
1. **PLANNING**（2 周）：
   - 与高校心理中心对接数据合作
   - 设计数据脱敏与隐私保护方案
   - 评估 Apple Health / Google Fit API 可行性

2. **IMPLEMENTING**（3-6 周）：
   - 接入 Apple Health / Google Fit API
   - 收集新数据并进行脱敏
   - 添加焦虑、压力等亚型标签
   - 重新训练 v3 模型（架构可保持 v2）

3. **VERIFYING**（2 周）：
   - v3 模型在测试集 F1 ≥0.88
   - 跨人群 AUC 方差 <0.05
   - 外部验证集 AUC ≥0.92

4. **MONITORING**（4 周）：
   - 金丝雀发布 v3 模型
   - 跟踪亚型场景表现

### Step 6: 阶段关卡验证

```python
def validate_phase2_gate() -> bool:
    """PHASE_2 → PHASE_3 关卡验证"""
    checks = [
        ("M-01 ~ M-04 全部 COMPLETED", all_items_completed()),
        ("14 天稳定性（无 P0 告警）", no_p0_alerts_for(days=14)),
        ("BERT 文本模型 F1 ≥0.97（长文本）", bert_f1_long_text() >= 0.97),
        ("漂移检测覆盖率 100%", drift_coverage() == 1.0),
        ("生理模型 v2 ECE <0.05", physiological_ece() < 0.05),
        ("数据集扩展至 10K+", dataset_size() >= 10000),
    ]
    return all(check for _, check in checks)
```

### Step 7: 阶段总结报告

生成 `.trae/mlopt/reports/phase-2-structural.md`：
- 4 项优化前后对比
- BERT 性能/延迟 trade-off 分析
- 漂移检测告警统计
- 数据集扩展成果
- 经验教训

---

## 📊 进度跟踪模板

```markdown
## Phase 2 Structural 进度 - {日期}

**总进度**: {X}/4 ({百分比}%)
**预计完成**: {日期}

### 优化项状态
| ID | 名称 | 状态 | 周期 | 金丝雀 | 关键指标 |
|----|------|------|------|--------|----------|
| M-01 | BERT 文本 | IMPLEMENTING | W3/8 | - | F1=0.96, P99=750ms |
| M-02 | 漂移检测 | MONITORING | W6/8 | 25% | 告警 3 次/周 |
| M-03 | v2 校准 | PLANNING | W1/10 | - | ECE=0.06 |
| M-04 | 数据集扩展 | BLOCKED | W2/12 | - | 等数据合作方 |
```

---

## 🚫 严禁事项

1. **严禁跳过 GPU 性能验证**：M-01 必须验证 CPU 降级场景
2. **严禁漂移检测阻塞主流程**：M-02 必须异步记录
3. **严禁使用未脱敏数据**：M-04 必须经过 PII 脱敏
4. **严禁校准集泄露**：M-03 校准集必须独立于训练集

---

## 🔗 关联

- **上游**：`mlopt-quickfix` (Phase 1)
- **下游**：`mlopt-architecture` (Phase 3)
- **依赖**：`mlopt-governance`（金丝雀、监控、告警）

---
name: mlopt-architecture
description: "Phase 3 executor for V4 ML optimization long-term architecture upgrades (L-01 to L-04). Invoke when user enters Phase 3, asks 'Keras融合生产化', '在线学习', '多中心验证', '可穿戴接入', or needs architecture progress."
---

# Skill: mlopt-architecture

> **V4 ML 优化 Phase 3 执行器**：4 项长期架构升级（3-6 月），目标模型架构演进。
> **调度者**：`mlopt-orchestrator`
> **基线文档**：`docs/模型性能综合评估与优化计划_v4.md` § 8.3

## 📋 技能描述

执行 V4 优化计划的 4 项长期架构升级（L-01 ~ L-04），周期 12-26 周。
本阶段涉及深度学习模型生产化、在线学习管道、多中心验证与可穿戴设备接入。

## 使用场景 (Usage)

- mlopt-orchestrator 进入 PHASE_3_ARCHITECTURE 时自动调度
- 用户指令："Keras 融合上线"、"在线学习管道"、"多中心验证"、"接入 Apple Health"
- 用户询问："L-01 进度"、"architecture 状态"

## 优化项清单 (4 项)

| ID | 名称 | 优先级 | 周期 | 关键资源 |
|----|------|--------|------|----------|
| L-01 | Keras 融合模型生产化 | P3 | 12-20 周 | GPU 服务器 |
| L-02 | 在线学习与持续训练 | P3 | 16-24 周 | ML 平台工程师 |
| L-03 | 多中心数据验证 | P3 | 20-26 周 | 合作机构 |
| L-04 | 可穿戴设备实时接入 | P3 | 20-26 周 | 移动端 + 后端 |

## 指令 (Instructions)

### Step 1: 进入条件验证

```
Gate: PHASE_2 → PHASE_3
- [ ] M-01 ~ M-04 全部 COMPLETED
- [ ] 14 天稳定性通过
- [ ] BERT 文本 F1 ≥0.97
- [ ] 漂移检测覆盖率 100%
```

### Step 2: L-01 Keras 融合模型生产化

**目标**：使用 `fusion_dnn_best` / `fusion_cross_modal_best` / `fusion_transformer_best` 替代加权融合，F1 +3-5%

**实施步骤**：
1. **PLANNING**（2 周）：
   - 评估 3 个 Keras 模型在真实数据上的表现
   - 设计 GPU 推理服务架构
   - 设计 CPU 回退到加权融合的策略
   - 设计 A/B 对比实验

2. **IMPLEMENTING**（4-6 周）：
   - 部署 GPU 推理服务器（TF Serving 或 ONNX Runtime）
   - 在 `predict_fusion()` 中添加 Keras 路径：
     ```python
     async def predict_fusion(self, ...):
         if keras_service_available:
             try:
                 return await self._predict_keras_fusion(...)
             except (TimeoutError, ServiceUnavailable):
                 pass
         return self._weighted_fusion(...)  # 回退
     ```
   - 实现 3 个 Keras 模型的 ensemble 策略
   - 添加 GPU 利用率监控

3. **VERIFYING**（2-3 周）：
   - 真实数据 F1 对比（Keras vs 加权）
   - P99 延迟 <1.2s 验证
   - GPU 故障降级测试

4. **MONITORING**（4-6 周）：
   - 5% → 25% → 100% 金丝雀
   - 每日对比 F1、延迟、资源
   - 若 F1 +3% 以上且 P99<1.2s → 全量切换

### Step 3: L-02 在线学习与持续训练

**目标**：模型月度自动再训练，每季度 F1 +1-2%

**实施步骤**：
1. **PLANNING**（3 周）：
   - 设计数据管道：用户授权数据 → 标注 → 训练集
   - 评估 Airflow / Prefect / Kubeflow
   - 设计模型版本管理（MLflow 或自建）
   - 设计自动评估阈值

2. **IMPLEMENTING**（6-8 周）：
   - 搭建数据管道：
     - 用户授权数据收集
     - 自动标注（基于高置信度预测 + 用户反馈）
     - 训练集构建
   - 配置月度训练任务（Airflow DAG）
   - 自动评估流程：
     ```python
     def auto_evaluate(new_model, baseline_model):
         metrics_new = evaluate(new_model, test_set)
         metrics_baseline = evaluate(baseline_model, test_set)
         return (
             metrics_new.f1 >= metrics_baseline.f1 * 0.98  # 不低于基线 98%
             and metrics_new.auc >= metrics_baseline.auc
         )
     ```
   - 通过阈值则进入金丝雀
   - 失败回滚到上一版本

3. **VERIFYING**（2-3 周）：
   - 模拟月度训练运行
   - 验证自动评估准确性
   - 验证回滚机制

4. **MONITORING**（4 周）：
   - 首月度训练上线
   - 跟踪 F1 变化趋势

### Step 4: L-03 多中心数据验证

**目标**：跨机构数据验证模型泛化性，AUC 跨集方差 <0.05

**实施步骤**：
1. **PLANNING**（4 周）：
   - 与 3+ 高校合作获取独立数据集
   - 设计数据共享协议（联邦学习 vs 集中验证）
   - 评估隐私保护方案（差分隐私 / 联邦学习）

2. **IMPLEMENTING**（8-10 周）：
   - 数据集 A：本校数据（基线）
   - 数据集 B：合作高校 1
   - 数据集 C：合作高校 2
   - 数据集 D：合作高校 3
   - 在每个数据集上独立评估 F1/AUC/校准
   - 计算跨集方差与泛化性指标

3. **VERIFYING**（2-3 周）：
   - 跨集 AUC 方差 <0.05
   - 无明显性能下降机构
   - 生成多中心验证报告

4. **MONITORING**（持续）：
   - 季度复评
   - 论文发表（学术合作）

### Step 5: L-04 可穿戴设备实时接入

**目标**：分钟级生理数据更新，预警提前 24h

**实施步骤**：
1. **PLANNING**（4 周）：
   - 评估 Apple HealthKit / Google Fit / Garmin API
   - 设计数据同步架构（已有 [ws.py](file:///e:/code/bysj/backend/app/core/ws.py) WebSocket）
   - 设计流式推理 + 滑动窗口
   - 设计异常值实时告警规则

2. **IMPLEMENTING**（8-10 周）：
   - 移动端 SDK 集成（iOS HealthKit / Android Health Connect）
   - 后端 WebSocket 推送管道
   - 流式推理服务：
     ```python
     async def stream_predict(device_data_stream):
         async for data in device_data_stream:
             window.update(data)
             if window.ready():
                 prediction = await model_engine._predict_physiological(window.features)
                 if prediction.risk_score > 80:
                     await alert_service.send_alert(user, prediction)
                 await websocket.send(prediction)
     ```
   - 异常值实时告警（心率/血压突增）
   - 滑动窗口特征工程

3. **VERIFYING**（2-3 周）：
   - 模拟设备数据流测试
   - 验证告警时延 <30s
   - 验证预警提前量 ≥24h

4. **MONITORING**（4-6 周）：
   - 真实用户灰度
   - 跟踪预警准确率

### Step 6: 阶段关卡验证

```python
def validate_phase3_gate() -> bool:
    """PHASE_3 → PHASE_4 关卡验证"""
    checks = [
        ("L-01 ~ L-04 全部 COMPLETED", all_items_completed()),
        ("30 天稳定性（无 P0 告警）", no_p0_alerts_for(days=30)),
        ("Keras 融合 F1 ≥加权融合 F1 +3%", keras_f1_improvement() >= 0.03),
        ("多中心 AUC 跨集方差 <0.05", multi_center_auc_variance() < 0.05),
        ("在线学习月度训练管道上线", online_learning_pipeline_active()),
        ("可穿戴预警提前量 ≥24h", wearable_alert_lead_time() >= 24),
    ]
    return all(check for _, check in checks)
```

### Step 7: 阶段总结报告

生成 `.trae/mlopt/reports/phase-3-architecture.md`：
- 4 项架构升级前后对比
- Keras 融合性能/资源 trade-off
- 在线学习管道运行情况
- 多中心验证发现
- 可穿戴接入用户反馈
- 学术成果（如有）

---

## 📊 进度跟踪模板

```markdown
## Phase 3 Architecture 进度 - {日期}

**总进度**: {X}/4 ({百分比}%)
**预计完成**: {日期}

### 优化项状态
| ID | 名称 | 状态 | 周期 | 金丝雀 | 关键指标 |
|----|------|------|------|--------|----------|
| L-01 | Keras 融合 | MONITORING | W14/20 | 25% | F1 +4%, P99=1.1s |
| L-02 | 在线学习 | IMPLEMENTING | W8/24 | - | 首月训练待跑 |
| L-03 | 多中心验证 | IMPLEMENTING | W10/26 | - | 3/4 机构数据已收 |
| L-04 | 可穿戴接入 | PLANNING | W4/26 | - | API 评估中 |
```

---

## 🚫 严禁事项

1. **严禁 GPU 单点**：L-01 必须有 CPU 回退方案
2. **严禁在线学习污染训练集**：L-02 必须有数据隔离
3. **严禁未授权数据共享**：L-03 必须有合作协议
4. **严禁可穿戴数据未脱敏**：L-04 必须经过 PII 处理
5. **严禁跳过学术伦理审查**：L-03 涉及人类被试需伦理批文

---

## 🔗 关联

- **上游**：`mlopt-structural` (Phase 2)
- **下游**：`mlopt-governance` (Phase 4)
- **依赖**：`mlopt-governance`（金丝雀、监控、告警）

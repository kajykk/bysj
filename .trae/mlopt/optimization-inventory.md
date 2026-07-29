# ML 优化项清单 (Optimization Inventory)

> **此文件由 mlopt-orchestrator 维护**
> **基线**: `docs/模型性能综合评估与优化计划_v4.md` § 7-8

## 元信息

- **创建时间**: 2026-07-19
- **最后更新**: 2026-07-20 (生产部署产物准备完成)
- **总优化项数**: 13 (S:5 + M:4 + L:4)
- **已完成**: 0
- **进行中**: 5 (S-01~S-05 VERIFYING, 部署产物就绪)
- **阻塞**: 0
- **已拒绝**: 0

## 优化项详情

### S-01: 启用生理模型 v2 替换 v1

| 字段 | 值 |
|------|-----|
| **优先级** | P0 |
| **阶段** | PHASE_1_QUICKFIX |
| **目标** | 生理单模态 F1: 0.694 → 0.854 (+23.1%) |
| **预期收益** | 融合 F1 +10% |
| **所需资源** | 1 名后端工程师 + 金丝雀基础设施 |
| **时间节点** | 第 1 周 |
| **依赖** | 无 |
| **关键文件** | `backend/app/core/model_engine_predict.py`, `backend/app/core/model_registry.py`, `backend/app/services/risk_service_assessment.py`, `backend/tests/api/test_model_predict.py` |
| **关键发现** | 实际推理已通过 `model_loader.py` 加载 v2 模型（`physiological_optimized/model.json`），但 `model_used` 字段、`MODEL_REGISTRY` lifecycle、测试断言仍标为 v1。S-01 实际工作范围：<br>1. 修正 `model_engine_predict.py:827` 的 `model_used` 字段为 `physiological_model_v2_dl`<br>2. 修正 `risk_service_assessment.py:227` 的字符串比较<br>3. 修正 `tests/api/test_model_predict.py:121` 的断言<br>4. 更新 `MODEL_REGISTRY` 中 `physiological_model_v2_dl` lifecycle → `default`，`physiological_risk_model` lifecycle → `deprecated` |
| **实施步骤** | 1. 修改 5 处代码引用<br>2. 运行回归测试<br>3. 更新 STATE.md<br>4. 7 天监控（标识修正类变更，金丝雀可选） |
| **验证标准** | (a) `model_used` 字段返回 `physiological_model_v2_dl`<br>(b) 419/421 测试通过<br>(c) `MODEL_REGISTRY` lifecycle 正确<br>(d) 无 P0/P1 告警 |
| **状态** | VERIFYING (80%, 部署产物就绪, 待生产金丝雀) |

### S-02: 切换默认结构化模型为 v1.23 external LR

| 字段 | 值 |
|------|-----|
| **优先级** | P0 |
| **阶段** | PHASE_1_QUICKFIX |
| **目标** | 真实场景 AUC: 0.867 → 0.913 (+5.3%) |
| **预期收益** | 消除合成数据过拟合 |
| **所需资源** | 1 名 ML 工程师 |
| **时间节点** | 第 1-2 周 |
| **依赖** | 无 |
| **关键文件** | `backend/app/core/model_engine_predict.py`, `backend/app/core/model_engine.py`, `models/v1.23_external_lr/`, `models/v1.24_adapter/` |
| **实施步骤** | 1. 修改 `predict_structured()` 默认 `model_used`<br>2. 加载 v1.23 模型 + scaler<br>3. 应用 v1.24 adapter 校准<br>4. v1.20 → deprecated（保留 30 天）<br>5. 金丝雀发布 |
| **验证标准** | (a) Mendeley PHQ-9 AUC ≥0.913<br>(b) ECE <0.05<br>(c) 419 用例通过 |
| **状态** | VERIFYING (85%, 部署产物就绪, 待生产金丝雀) |

### S-03: 清理 v1.21 deprecated 模型

| 字段 | 值 |
|------|-----|
| **优先级** | P1 |
| **阶段** | PHASE_1_QUICKFIX |
| **目标** | 注册表 12 → 8 个条目 |
| **预期收益** | 降低误用风险 |
| **所需资源** | 0.5 人天 |
| **时间节点** | 第 2 周 |
| **依赖** | S-02 已 COMPLETED |
| **关键文件** | `backend/app/core/model_registry.py`, `backend/app/core/model_compatibility.py`, `models/artifacts/structured_v1.21/` |
| **实施步骤** | 1. 全代码搜索 v1.21 引用<br>2. 删除 4 个 v1.21 注册条目<br>3. 归档模型文件到 _archive/<br>4. 更新兼容性矩阵<br>5. 全量回归测试 |
| **验证标准** | (a) 注册表条目 8 个<br>(b) 回归测试 100% 通过 |
| **状态** | VERIFYING (90%, 部署产物就绪, 待生产金丝雀) |

### S-04: 拆分健康检查端点

| 字段 | 值 |
|------|-----|
| **优先级** | P1 |
| **阶段** | PHASE_1_QUICKFIX |
| **目标** | 健康检查冷启动: 8s → <2s (live <30ms) |
| **预期收益** | 消除探针超时与滚动更新阻塞 |
| **所需资源** | 1 人天 |
| **时间节点** | 第 2 周 |
| **依赖** | 无 |
| **关键文件** | `backend/app/main.py`, `backend/tests/performance/test_api_latency.py`, `backend/load_tests/locustfile.py` |
| **实施步骤** | 1. 新增 /health/live (轻量)<br>2. 现有 /health → /health/ready<br>3. 异步缓存深度检查 5s<br>4. 更新探针配置与测试<br>5. 保留 /health 兼容性 30 天 |
| **验证标准** | (a) live P99 <30ms<br>(b) ready P99 <2s |
| **状态** | VERIFYING (90%, 部署产物就绪, 待生产金丝雀) |

### S-05: 启用模型推理结果缓存

| 字段 | 值 |
|------|-----|
| **优先级** | P1 |
| **阶段** | PHASE_1_QUICKFIX |
| **目标** | 缓存命中率 ≥30%, 重复查询延迟 <10ms |
| **预期收益** | 高频查询延迟 -50% |
| **所需资源** | 1 人天 |
| **时间节点** | 第 2-3 周 |
| **依赖** | 无 |
| **关键文件** | `backend/app/services/model_predict_service.py` |
| **实施步骤** | 1. 验证 _ML_INFERENCE_CACHE_TTL=60 生效<br>2. 完善 make_cache_key (user_id + 特征哈希)<br>3. 三端点接入缓存<br>4. 添加缓存命中率指标<br>5. A/B 验证 |
| **验证标准** | (a) 缓存命中率 ≥30%<br>(b) 重复响应 <10ms |
| **状态** | VERIFYING (90%, 部署产物就绪, 待生产金丝雀) |

### M-01: 启用 BERT 文本模型

| 字段 | 值 |
|------|-----|
| **优先级** | P2 |
| **阶段** | PHASE_2_STRUCTURAL |
| **目标** | 长文本 F1 +3% |
| **预期收益** | 多语言/长文本场景提升 |
| **所需资源** | 1 名 ML 工程师 + GPU 推理服务器 |
| **时间节点** | 第 4-8 周 |
| **依赖** | GPU 资源 |
| **关键文件** | `backend/app/core/model_engine_predict.py`, `models/text/bert_text_classifier` |
| **验证标准** | (a) 长文本 F1 +3%<br>(b) P99 <800ms |
| **状态** | PROPOSED |

### M-02: 漂移检测生产化

| 字段 | 值 |
|------|-----|
| **优先级** | P2 |
| **阶段** | PHASE_2_STRUCTURAL |
| **目标** | 100% 模型覆盖漂移监控, MTTD <1h |
| **预期收益** | 72h 内发现分布偏移 |
| **所需资源** | 1 名后端工程师 + Alertmanager |
| **时间节点** | 第 4-8 周 |
| **依赖** | Alertmanager 已部署 |
| **关键文件** | `backend/app/main.py`, `backend/app/ml/drift_detector.py`, `backend/app/ml/model_monitor.py` |
| **验证标准** | (a) 漂移覆盖率 100%<br>(b) MTTD <1h |
| **状态** | PROPOSED |

### M-03: 生理模型 v2 校准

| 字段 | 值 |
|------|-----|
| **优先级** | P2 |
| **阶段** | PHASE_2_STRUCTURAL |
| **目标** | ECE <0.05, Brier <0.15 |
| **预期收益** | 高分组实际抑郁率 70% → 85%+ |
| **所需资源** | 1 名 ML 工程师 |
| **时间节点** | 第 6-10 周 |
| **依赖** | S-01 已 COMPLETED |
| **关键文件** | `models/artifacts/physiological_optimized/`, `models/v1.24_adapter/` |
| **验证标准** | (a) ECE <0.05<br>(b) Brier <0.15 |
| **状态** | PROPOSED |

### M-04: 扩展生理数据集

| 字段 | 值 |
|------|-----|
| **优先级** | P2 |
| **阶段** | PHASE_2_STRUCTURAL |
| **目标** | 训练样本 2K → 10K+, 覆盖亚型 |
| **预期收益** | F1 +3-5% |
| **所需资源** | 数据合作 + 1 名 ML 工程师 |
| **时间节点** | 第 6-12 周 |
| **依赖** | 数据合作方 |
| **关键文件** | `backend/app/ml/model.py`, 数据管道 |
| **验证标准** | (a) v3 F1 ≥0.88<br>(b) 跨人群 AUC 方差 <0.05 |
| **状态** | PROPOSED |

### L-01: Keras 融合模型生产化

| 字段 | 值 |
|------|-----|
| **优先级** | P3 |
| **阶段** | PHASE_3_ARCHITECTURE |
| **目标** | 融合 F1 +3-5% |
| **预期收益** | 深度学习捕获非线性交互 |
| **所需资源** | GPU 服务器 + 1 名 ML 工程师 |
| **时间节点** | 第 12-20 周 |
| **依赖** | GPU 服务器 |
| **关键文件** | `models/keras/`, `backend/app/ml/fusion_engine.py` |
| **验证标准** | (a) F1 +3%<br>(b) P99 <1.2s |
| **状态** | PROPOSED |

### L-02: 在线学习与持续训练

| 字段 | 值 |
|------|-----|
| **优先级** | P3 |
| **阶段** | PHASE_3_ARCHITECTURE |
| **目标** | 月度自动再训练, 季度 F1 +1-2% |
| **预期收益** | 模型持续进化 |
| **所需资源** | ML 平台工程师 + 数据工程 |
| **时间节点** | 第 16-24 周 |
| **依赖** | 数据管道基础设施 |
| **关键文件** | 新建 ML pipeline |
| **验证标准** | (a) 月度训练管道运行<br>(b) F1 持续提升 |
| **状态** | PROPOSED |

### L-03: 多中心数据验证

| 字段 | 值 |
|------|-----|
| **优先级** | P3 |
| **阶段** | PHASE_3_ARCHITECTURE |
| **目标** | 跨机构 AUC 方差 <0.05 |
| **预期收益** | 模型通用性验证, 学术声誉 |
| **所需资源** | 合作机构 + 数据治理 |
| **时间节点** | 第 20-26 周 |
| **依赖** | 合作机构协议 |
| **关键文件** | 验证报告 |
| **验证标准** | (a) 跨集 AUC 方差 <0.05 |
| **状态** | PROPOSED |

### L-04: 可穿戴设备实时接入

| 字段 | 值 |
|------|-----|
| **优先级** | P3 |
| **阶段** | PHASE_3_ARCHITECTURE |
| **目标** | 分钟级生理数据更新, 预警提前 24h |
| **预期收益** | 从问卷式 → 连续监测 |
| **所需资源** | 1 前端 + 1 后端 + 移动端 |
| **时间节点** | 第 20-26 周 |
| **依赖** | 移动端开发 |
| **关键文件** | `backend/app/core/ws.py`, 新建 SDK |
| **验证标准** | (a) 告警时延 <30s<br>(b) 预警提前 ≥24h |
| **状态** | PROPOSED |

## 拒绝记录

| ID | 名称 | 拒绝原因 | 决策者 | 日期 |
|----|------|----------|--------|------|
| - | - | - | - | - |

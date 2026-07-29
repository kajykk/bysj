# Phase 0 基线建立 + S-01 VERIFYING 报告

> **生成时间**: 2026-07-19
> **当前阶段**: PHASE_1_QUICKFIX (Round 1)
> **总进度**: 1/13 优化项进入 VERIFYING (7.7%)

## 本回合完成工作

### Phase 0: 基线建立 ✅ 完成

**完成内容**:
1. 初始化 `.trae/mlopt/STATE.md` - 主状态文件（5 阶段+13 项状态表+关卡清单+决策记录+风险登记册）
2. 初始化 `.trae/mlopt/optimization-inventory.md` - 13 项优化详情（含 S-01 关键发现）
3. 初始化 `.trae/mlopt/metrics-baseline.md` - V4 指标基线（4 类模型+性能+资源+测试+稳定性）

**关卡验证 PHASE_0 → PHASE_1** (4/4 通过):
- ✅ metrics-baseline.md 已写入 4 类模型基线
- ✅ optimization-inventory.md 已初始化 13 个优化项
- ✅ 测试基线: 446 passed / 2 skipped (V4 报告 419，实测 446，超出基线 27 个)
- ✅ 性能基线: health<200ms, fusion<100ms, list<500ms 全部达标

**关键发现**: 实际测试用例数 446 比 V4 报告记录的 419 多 27 个，基线比预期更强。

### S-01: 启用生理模型 v2 替换 v1 — VERIFYING (80%)

**关键发现**: 实际推理已通过 `app/ml/model_loader.py` 加载 v2 模型（`physiological_optimized/model.json`），但 `predict_physiological` 返回的 `model_used` 字段、`MODEL_REGISTRY` lifecycle、测试断言仍标为 v1。S-01 实际工作范围从"启用 v2 替换 v1"缩减为"标识修正 + 生命周期更新"。

**代码变更（4 处）**:

| 文件 | 行号 | 变更 |
|------|------|------|
| `backend/app/core/model_engine_predict.py` | 827 | `model_used` 字段从 `"physiological_risk_model"` → `"physiological_model_v2_dl"` |
| `backend/app/services/risk_service_assessment.py` | 227 | 字符串比较从 `"physiological_risk_model"` → `"physiological_model_v2_dl"` |
| `backend/tests/api/test_model_predict.py` | 121 | 断言从 `"physiological_risk_model"` → `"physiological_model_v2_dl"` |
| `backend/app/core/model_registry.py` | 223-274 | `physiological_model_v2_dl` 添加 `lifecycle="default"`；新增 `physiological_risk_model` 显式注册，`lifecycle="deprecated"`、`enabled=False` |

**验证结果**:

| 测试套件 | 用例数 | 通过 | 跳过 | 失败 | 耗时 |
|----------|--------|------|------|------|------|
| api/test_model_predict + test_model_engine + test_fusion_engine + expected_risk + select_best_model + compare_text_models | 156 | 154 | 2 | 0 | 5.94s |
| tests/ml/ + services/test_drift_detector + test_evaluate_model + test_model_monitor + test_qa011_resource_usage | 286 | 286 | 0 | 0 | 31.09s |
| tests/performance/test_api_latency | 3 | 3 | 0 | 0 | 10.49s |
| tests/test_model_registry + test_unified_model_interface | 21 | 21 | 0 | 0 | 1.12s |
| **合计** | **466** | **464** | **2** | **0** | **48.64s** |

**验证标准达成** (4/4):
- ✅ (a) `model_used` 字段返回 `physiological_model_v2_dl`
- ✅ (b) 419+ 测试通过（实际 464 passed）
- ✅ (c) `MODEL_REGISTRY` lifecycle 正确（v2=default, v1=deprecated, enabled=False）
- ✅ (d) 无 P0/P1 告警（性能测试 3/3 通过）

**剩余工作**:
- 金丝雀三级推进（5% → 25% → 100%），每级 ≥24h — 需生产环境
- 7 天观察期无 P0/P1 告警 — 需时间累积

由于当前为开发环境，金丝雀与观察期需待生产部署后完成。S-01 当前状态为 VERIFYING，待金丝雀完成且观察期通过后切换为 COMPLETED。

## 下一步计划

### 短期（下一回合）

1. **S-02: 切换默认结构化模型为 v1.23 external LR** (P0)
   - 阅读 `predict_structured()` 完整实现
   - 设计 v1.23 加载逻辑 + v1.24 adapter 校准
   - 修改默认 `model_used` + lifecycle
   - 验证 Mendeley PHQ-9 AUC ≥0.913

2. **S-03: 清理 v1.21 deprecated 模型** (P1，依赖 S-02)
   - 全代码搜索 v1.21 引用
   - 删除 4 个 v1.21 注册条目
   - 归档模型文件到 _archive/

### 中期（本周内）

3. **S-04: 拆分健康检查端点** (P1)
4. **S-05: 启用推理结果缓存** (P1)

### 长期（按计划推进）

5. Phase 2: M-01 ~ M-04（BERT、漂移检测、校准、数据集扩展）
6. Phase 3: L-01 ~ L-04（Keras 融合、在线学习、多中心、可穿戴）
7. Phase 4: 90 天治理期 + V5 报告

## 风险与阻塞

| 风险 | 状态 | 缓解措施 |
|------|------|----------|
| S-01 金丝雀需生产环境 | 已记录 | 待生产部署后补走流程 |
| S-02 v1.23 模型文件就绪待验证 | OPEN | 下一回合先验证文件完整性 |
| GPU 资源不足影响 M-01/L-01 | OPEN | 提前评估云服务方案 |
| 数据合作方延迟影响 M-04/L-03 | OPEN | 多方接洽 |

## 总结

本回合从 INIT 推进至 PHASE_1_QUICKFIX，完成 Phase 0 基线建立（4/4 关卡通过），并将 S-01 推进至 VERIFYING（代码完成 + 464 测试通过，待金丝雀）。1/13 优化项进入验证阶段，符合预期进度。

# 测试计划 (Test Plan)

> **迭代**: v1.5-performance-observability-insights
> **版本**: Final Locked
> **日期**: 2026-04-28
> **状态**: ✅ 已终定锁定，进入开发阶段
> **基于文档**: 01-requirements.md, 02-architecture.md, 04-ralph-tasks.md
> **测试框架**: pytest (后端单元/集成) + Vitest (前端单元) + Playwright (E2E) + schemathesis (契约) + locust (性能)

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行测试用例。严禁跳跃或乱序执行。

---

## 测试用例 ID 格式

`[TC-<MODULE>-<TYPE>-<NUMBER>]`

- **Modules**: `MON` (监控), `CAN` (灰度), `VAL` (验证), `RPT` (报告), `FEO` (前端优化), `VIZ` (可视化), `FBC` (回退容错), `DRF` (漂移修复), `DEP` (依赖治理)
- **Types**: `HP` (Happy Path), `SP` (Sad Path), `EC` (Edge Case), `UI` (UI/UX), `PERF` (性能), `SEC` (安全)

---

## 1. 监控与可观测性 (Monitoring) — Module: MON

### 1.1 模型成功率监控

**Happy Path:**
- [ ] `[TC-MON-HP-001]` 正常推理请求被记录为 MODEL_SUCCESS，成功率计算正确 (P0)
- [ ] `[TC-MON-HP-002]` 按小时粒度查询成功率趋势，返回正确的时间序列数据 (P0)
- [ ] `[TC-MON-HP-003]` 按天粒度查询成功率趋势，数据聚合正确 (P1)
- [ ] `[TC-MON-HP-004]` 多版本模型分别统计成功率，数据隔离正确 (P1)

**Sad Path:**
- [ ] `[TC-MON-SP-001]` 模型推理抛出异常，记录为 MODEL_FALLBACK，成功率下降 (P0)
- [ ] `[TC-MON-SP-002]` 数据库连接失败，监控指标不丢失，写入队列待恢复 (P1)

**Edge Cases:**
- [ ] `[TC-MON-EC-001]` 零请求时段，成功率返回 null 而非除零错误 (P1)
- [ ] `[TC-MON-EC-002]` 跨天查询边界，时间范围包含完整的小时/天 (P2)

### 1.2 回退触发率监控

**Happy Path:**
- [ ] `[TC-MON-HP-005]` 回退事件正确记录 fallback_reason 和 model_version (P0)
- [ ] `[TC-MON-HP-006]` 查询回退统计，top_reason 排序正确 (P1)

**Sad Path:**
- [ ] `[TC-MON-SP-003]` 回退原因未定义时，记录为 UNKNOWN (P1)

### 1.3 输入异常告警

**Happy Path:**
- [ ] `[TC-MON-HP-007]` NaN 输入触发 INPUT_ANOMALY 记录 (P0)
- [ ] `[TC-MON-HP-008]` 缺失必填字段触发 INPUT_ANOMALY 记录 (P0)
- [ ] `[TC-MON-HP-009]` 空文本输入触发 INPUT_ANOMALY 记录 (P1)

**Edge Cases:**
- [ ] `[TC-MON-EC-003]` 同时存在多种异常，记录所有异常类型 (P2)

### 1.4 漂移告警监控

**Happy Path:**
- [ ] `[TC-MON-HP-010]` 漂移检测触发后，DriftAlert 记录 severity 正确 (P0)
- [ ] `[TC-MON-HP-011]` 查询未解决的 HIGH severity 告警，过滤正确 (P1)
- [ ] `[TC-MON-HP-012]` 解决告警后，resolved_at 字段更新 (P1)

**Sad Path:**
- [ ] `[TC-MON-SP-004]` 漂移检测除零错误，不抛异常，记录 WARNING severity (P0)

### 1.5 监控面板 API

**Happy Path:**
- [ ] `[TC-MON-HP-013]` GET /monitoring/dashboard-summary 返回聚合数据，延迟 < 5s (P0)
- [ ] `[TC-MON-HP-014]` 面板数据包含模型效果/服务健康/回退与异常三大板块 (P1)
- [ ] `[TC-MON-HP-015]` GET /monitoring/request-details 支持从告警下钻到明细请求 (P1)

**Security:**
- [ ] `[TC-MON-SEC-001]` 非 Admin 用户访问监控接口返回 403 (P0)

### 1.6 告警生命周期 (NEW)

**Happy Path:**
- [ ] `[TC-MON-HP-016]` 告警状态流转: TRIGGERED -> ACKNOWLEDGED -> RESOLVED -> CLOSED (P0)
- [ ] `[TC-MON-HP-017]` CRITICAL 告警触发短信+邮件+站内信通知 (P0)
- [ ] `[TC-MON-HP-018]` HIGH 告警触发邮件+站内信通知 (P1)
- [ ] `[TC-MON-HP-019]` MEDIUM 告警仅触发站内信通知 (P1)
- [ ] `[TC-MON-HP-020]` LOW 告警纳入日报汇总 (P2)

**Sad Path:**
- [ ] `[TC-MON-SP-005]` 通知渠道配置缺失时，降级为站内信 (P1)

---

## 2. 灰度发布 (Canary) — Module: CAN

### 2.1 灰度创建与流量分配

**Happy Path:**
- [ ] `[TC-CAN-HP-001]` 创建 1% 灰度发布，状态为 ACTIVE，流量比例正确 (P0)
- [ ] `[TC-CAN-HP-002]` 1000 次请求中，灰度版本接收约 10 次 (误差 < 1%) (P0)
- [ ] `[TC-CAN-HP-003]` 同一用户 ID 始终路由到同一版本 (一致性) (P1)
- [ ] `[TC-CAN-HP-004]` 按 step_plan 逐步扩量到 5% / 25% / 50% / 100% (P1)
- [ ] `[TC-CAN-HP-005]` Redis 动态调整流量比例，无需重启服务 (P1)

**Sad Path:**
- [ ] `[TC-CAN-SP-001]` 创建灰度时版本号不存在，返回 400 (P1)
- [ ] `[TC-CAN-SP-002]` 同时存在多个 ACTIVE 灰度，返回 409 冲突 (P1)

**Edge Cases:**
- [ ] `[TC-CAN-EC-001]` 流量比例为 0%，所有请求走基线版本 (P2)
- [ ] `[TC-CAN-EC-002]` 流量比例为 100%，等同于全量发布 (P2)

### 2.2 自动回滚

**Happy Path:**
- [ ] `[TC-CAN-HP-006]` 回退率超过 5% 阈值，自动触发回滚，状态变为 ROLLED_BACK (P0)
- [ ] `[TC-CAN-HP-007]` 漂移告警超过 10 次/小时，自动触发回滚 (P0)
- [ ] `[TC-CAN-HP-008]` 平均延迟超过 500ms，自动触发回滚 (P0)
- [ ] `[TC-CAN-HP-009]` 回滚后流量全部切回基线版本 (P0)
- [ ] `[TC-CAN-HP-010]` 自动回滚触发后，Admin 收到站内信+邮件通知 (P0)

**Sad Path:**
- [ ] `[TC-CAN-SP-003]` 自动回滚触发时基线版本不可用，返回 503 (P1)
- [ ] `[TC-CAN-SP-004]` 阈值配置缺失时，使用默认值 (P2)

### 2.3 手动回滚与日志

**Happy Path:**
- [ ] `[TC-CAN-HP-011]` Admin 手动调用回滚，记录 rollback_reason 和 triggered_by (P0)
- [ ] `[TC-CAN-HP-012]` 人工回滚可覆盖自动回滚状态 (P1)
- [ ] `[TC-CAN-HP-013]` 查询灰度历史记录，版本切换日志完整可追溯 (P1)

**Edge Cases:**
- [ ] `[TC-CAN-EC-003]` 已回滚的灰度再次调用回滚，返回 400 (P2)

---

## 3. 真实样本验证 (Validation) — Module: VAL

### 3.1 离线验证执行

**Happy Path:**
- [ ] `[TC-VAL-HP-001]` 提交验证任务，返回 validation_id 和 RUNNING 状态 (P0)
- [ ] `[TC-VAL-HP-002]` 验证完成后，所有指标 (Accuracy/Precision/Recall/F1/AUC/MAE/RMSE) 计算正确 (P0)
- [ ] `[TC-VAL-HP-003]` 与基线版本对比，f1_delta / regression_samples / improvement_samples 计算正确 (P0)
- [ ] `[TC-VAL-HP-004]` 验证集 >= 500 条样本，覆盖所有风险等级 (P0)

**Sad Path:**
- [ ] `[TC-VAL-SP-001]` 数据集路径不存在，返回 404 (P1)
- [ ] `[TC-VAL-SP-002]` 数据集格式错误，返回 400 (P1)

### 3.2 异常样本分析

**Happy Path:**
- [ ] `[TC-VAL-HP-005]` NaN 样本记录 failure_reason 为 NaN_in_feature_xxx (P0)
- [ ] `[TC-VAL-HP-006]` 缺字段样本记录 failure_reason 为 MISSING_FIELD_xxx (P0)
- [ ] `[TC-VAL-HP-007]` 异常样本清单明确，失败原因可定位 (P0)

**Edge Cases:**
- [ ] `[TC-VAL-EC-001]` 全部样本异常，验证任务完成但 metrics 为 null (P2)

### 3.3 灰度建议

**Happy Path:**
- [ ] `[TC-VAL-HP-008]` F1 >= 0.78 时，canary_recommendation 为 "建议灰度" (P0)
- [ ] `[TC-VAL-HP-009]` F1 < 0.78 时，canary_recommendation 为 "不建议灰度" (P0)

---

## 4. 报告导出 (Report) — Module: RPT

### 4.1 PDF 导出

**Happy Path:**
- [ ] `[TC-RPT-HP-001]` 用户风险报告 PDF 生成成功，包含趋势图和建议 (P0)
- [ ] `[TC-RPT-HP-002]` PDF 生成时间 < 3s (P0)
- [ ] `[TC-RPT-HP-003]` 咨询师报告包含多用户汇总数据 (P1)
- [ ] `[TC-RPT-HP-004]` 管理分析报告包含系统级指标 (P1)

**Sad Path:**
- [ ] `[TC-RPT-SP-001]` 用户无权限访问他人报告，返回 403 (P0)
- [ ] `[TC-RPT-SP-002]` 用户数据不存在，PDF 生成失败返回 404 (P1)

### 4.2 Excel 导出

**Happy Path:**
- [ ] `[TC-RPT-HP-005]` 10000 条数据 Excel 导出成功，无内存溢出 (P0)
- [ ] `[TC-RPT-HP-006]` 列筛选和过滤条件生效，导出数据正确 (P0)
- [ ] `[TC-RPT-HP-007]` 空筛选结果导出空表格 (含表头) (P1)

**Performance:**
- [ ] `[TC-RPT-PERF-001]` 10000 条数据导出耗时 < 10s (P1)

---

## 5. 前端性能优化 (Frontend Optimization) — Module: FEO

### 5.1 路由懒加载

**Happy Path:**
- [ ] `[TC-FEO-HP-001]` 首屏仅加载当前页面 chunk，其他页面按需加载 (P0)
- [ ] `[TC-FEO-HP-002]` 路由切换时，新页面 chunk 加载成功 (P0)

**Performance:**
- [ ] `[TC-FEO-PERF-001]` 初始打包体积减少 20% (相比 v1.4) (P0)

### 5.2 虚拟列表

**Happy Path:**
- [ ] `[TC-FEO-HP-003]` 1000 条数据列表，仅渲染可视区域 DOM 节点 (P0)
- [ ] `[TC-FEO-HP-004]` 滚动时，节点复用无闪烁 (P1)

**Performance:**
- [ ] `[TC-FEO-PERF-002]` 长列表滚动帧率 >= 50fps (P0)

### 5.3 图片懒加载

**Happy Path:**
- [ ] `[TC-FEO-HP-005]` 视口外图片不加载，进入视口后加载 (P0)
- [ ] `[TC-FEO-HP-006]` 图片加载前显示占位图 (P1)

### 5.4 骨架屏

**Happy Path:**
- [ ] `[TC-FEO-HP-007]` 页面加载时显示骨架屏 (P0)
- [ ] `[TC-FEO-HP-008]` 数据加载完成后，骨架屏平滑过渡到真实内容 (P1)

### 5.5 前端性能监控

**Happy Path:**
- [ ] `[TC-FEO-HP-009]` FCP/LCP/FID/CLS/TTFB 指标采集正确 (P1)
- [ ] `[TC-FEO-HP-010]` 性能指标上报到后端成功 (P1)

**Performance:**
- [ ] `[TC-FEO-PERF-003]` 首屏加载时间降低 30% (相比 v1.4) (P0)
- [ ] `[TC-FEO-PERF-004]` FCP < 2.5s, LCP < 4.0s (P0)

---

## 6. 数据可视化 (Visualization) — Module: VIZ

### 6.1 ECharts 图表

**Happy Path:**
- [ ] `[TC-VIZ-HP-001]` 风险趋势图表正确渲染，支持时间维度缩放 (P0)
- [ ] `[TC-VIZ-HP-002]` 模型性能 Dashboard 显示准确率/AUC/F1/各版本对比 (P0)
- [ ] `[TC-VIZ-HP-003]` 系统健康监控图表显示 API 延迟/错误率/吞吐量 (P0)
- [ ] `[TC-VIZ-HP-004]` 图表支持导出为图片 (P1)

**Sad Path:**
- [ ] `[TC-VIZ-SP-001]` 无数据时显示空状态提示，不报错 (P1)

**UI:**
- [ ] `[TC-VIZ-UI-001]` 图表响应式，窗口缩放自适应 (P0)
- [ ] `[TC-VIZ-UI-002]` 移动端图表可触摸缩放 (P1)

---

## 7. 回退与容错 (Fallback & Resilience) — Module: FBC

### 7.1 模型加载失败回退

**Happy Path:**
- [ ] `[TC-FBC-HP-001]` 模型文件损坏时，自动回退到启发式规则，返回有效结果 (P0)
- [ ] `[TC-FBC-HP-002]` 回退事件记录到 MonitoringLog，原因正确 (P0)

### 7.2 依赖缺失回退

**Happy Path:**
- [ ] `[TC-FBC-HP-003]` 无 PyTorch 环境，torch 模型自动回退到启发式规则 (P0)
- [ ] `[TC-FBC-HP-004]` 系统正常启动，不依赖 torch (P0)

### 7.3 预测异常回退

**Happy Path:**
- [ ] `[TC-FBC-HP-005]` 模型输出 NaN，自动回退到启发式规则 (P0)
- [ ] `[TC-FBC-HP-006]` 模型输出 Inf，自动回退到启发式规则 (P0)
- [ ] `[TC-FBC-HP-007]` 预测概率超出 [0,1] 范围，自动回退 (P0)

### 7.4 延迟超时回退

**Happy Path:**
- [ ] `[TC-FBC-HP-008]` 推理延迟 > 200ms，触发超时告警并回退 (P0)
- [ ] `[TC-FBC-HP-009]` 回退后延迟 < 50ms (P1)

---

## 8. 漂移检测边界修复 (Drift Fix) — Module: DRF

### 8.1 除零错误修复

**Happy Path:**
- [ ] `[TC-DRF-HP-001]` 空分布输入，漂移检测返回 0 或 null，不抛异常 (P0)
- [ ] `[TC-DRF-HP-002]` 单值分布输入，漂移检测返回 0 或 null，不抛异常 (P0)
- [ ] `[TC-DRF-HP-003]` 极端分布输入，无 RuntimeWarning (P0)

**Edge Cases:**
- [ ] `[TC-DRF-EC-001]` 两个分布完全相同，PSI = 0 (P1)
- [ ] `[TC-DRF-EC-002]` 两个分布完全不同，PSI 计算正确 (P1)

---

## 9. 依赖治理 (Dependency Governance) — Module: DEP

### 9.1 sklearn 版本治理

**Happy Path:**
- [ ] `[TC-DEP-HP-001]` 模型加载时无 sklearn 版本 warning (P0)
- [ ] `[TC-DEP-HP-002]` 兼容性检查脚本正确识别版本不匹配 (P1)

### 9.2 PyTorch 可选依赖

**Happy Path:**
- [ ] `[TC-DEP-HP-003]` config.PYTORCH_AVAILABLE 正确反映环境状态 (P0)
- [ ] `[TC-DEP-HP-004]` torch 缺失时，fallback 行为与 torch 存在时一致 (P0)

---

## 测试统计

| Module | 用例数 | P0 | P1 | P2 |
|--------|--------|----|----|----|
| MON (监控) | 21 | 10 | 8 | 3 |
| CAN (灰度) | 16 | 8 | 4 | 4 |
| VAL (验证) | 11 | 7 | 2 | 2 |
| RPT (报告) | 8 | 4 | 3 | 1 |
| FEO (前端优化) | 15 | 6 | 6 | 3 |
| VIZ (可视化) | 6 | 3 | 2 | 1 |
| FBC (回退容错) | 9 | 8 | 1 | 0 |
| DRF (漂移修复) | 5 | 3 | 2 | 0 |
| DEP (依赖治理) | 4 | 3 | 1 | 0 |
| **总计** | **95** | **52** | **29** | **14** |

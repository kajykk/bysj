# Ralph 任务列表 (Implementation Plan)

> **迭代**: v1.5-performance-observability-insights
> **版本**: Final Locked
> **日期**: 2026-04-28
> **状态**: ✅ 已终定锁定，进入开发阶段

<!--
AI 指令:
1. 任务必须原子化 (1-4小时粒度)，严禁大颗粒度任务。
2. 必须遵循 Infrastructure -> Backend -> Frontend -> QA 的依赖顺序。
3. 执行阶段：必须激活 ralph-task-executor Skill。每完成一个任务，必须立即更新此文件。
4. 只有当代码已实现且经过验证后，才能将 "[ ]" 改为 "[x]"。
5. 顺序强制: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。
-->

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。

## 任务状态图例
- [ ] 待开始 (Pending)
- [x] 已完成 (Completed)
- [~] 进行中 (In Progress)
- [-] 阻塞 (Blocked)

---

## Phase 1: 基础设施与数据层 (Infrastructure & Data Layer)

### 1.1 数据库模型与迁移
- [x] **T-INFRA-001** 创建 MonitoringLog 数据模型
  - 定义 SQLAlchemy 模型: event_type, model_version, user_id, request_payload, response_summary, fallback_reason, latency_ms, created_at
  - 添加复合索引: (event_type, created_at), (model_version, created_at)
  - 生成 Alembic 迁移脚本
  - **编写单元测试**: 模型字段验证、索引存在性检查

- [x] **T-INFRA-002** 创建 CanaryRecord 数据模型
  - 定义 SQLAlchemy 模型: version, traffic_percent, status, auto_rollback_thresholds, triggered_by, started_at, ended_at, rollback_reason
  - 添加索引: (status, started_at), (version, created_at)
  - 生成 Alembic 迁移脚本
  - **编写单元测试**: 模型字段验证、状态枚举约束

- [x] **T-INFRA-003** 创建 ValidationResult 数据模型
  - 定义 SQLAlchemy 模型: sample_id, model_version, ground_truth, prediction, confidence, is_correct, failure_reason, created_at
  - 添加索引: (model_version, created_at), (is_correct, created_at)
  - 生成 Alembic 迁移脚本
  - **编写单元测试**: 模型字段验证、布尔索引

- [x] **T-INFRA-004** 增强 DriftAlert 数据模型
  - 新增 severity 字段 (Enum: LOW, MEDIUM, HIGH, CRITICAL)
  - 新增 resolved_at 字段
  - 更新 Alembic 迁移脚本
  - **编写单元测试**: severity 枚举约束、resolved_at 可空性

### 1.2 配置与依赖治理
- [x] **T-INFRA-005** 统一 sklearn 训练/推理版本
  - 检查当前 requirements.txt 中的 sklearn 版本
  - 确认训练环境与推理环境版本一致 (目标 1.3.x)
  - 更新 requirements.txt 并锁定版本
  - 消除模型加载时的版本 warning
  - **编写单元测试**: 模型加载无 warning

- [x] **T-INFRA-006** 明确 PyTorch 可选依赖策略
  - 在 requirements.txt 中使用 extras_require 区分 torch 依赖
  - 在 config.py 中增加 PYTORCH_AVAILABLE 运行时检测
  - 确保 fallback 行为在 torch 缺失时一致
  - **编写单元测试**: 无 torch 环境自动回退到启发式规则

- [x] **T-INFRA-007** 模型序列化兼容性文档
  - 梳理当前所有模型的序列化格式 (joblib/pickle/onnx)
  - 记录各模型的 sklearn/torch/transformers 版本要求
  - 编写模型加载兼容性检查脚本
  - **编写单元测试**: 兼容性检查脚本正确识别版本不匹配

---

## Phase 2: 后端核心功能 (Backend Core)

### 2.1 监控与可观测性
- [x] **T-BE-001** 实现 Observability 指标收集器
  - 实现 inference_latency 直方图采集
  - 实现 model_success / fallback 计数器
  - 实现 input_anomaly 检测与计数
  - 所有指标写入 MonitoringLog 表 (异步批处理，每 30s flush)
  - **编写单元测试**: 各指标采集正确性、数据库写入验证

- [x] **T-BE-002** 实现 Monitoring API 路由
  - GET /monitoring/model-success-rate (支持 granularity)
  - GET /monitoring/fallback-stats
  - GET /monitoring/drift-alerts (支持 severity/resolved 过滤)
  - GET /monitoring/dashboard-summary (聚合面板数据)
  - GET /monitoring/request-details (从告警下钻到明细请求)
  - **编写单元测试**: 各接口响应格式、过滤逻辑、权限校验

- [x] **T-BE-003** 实现输入异常检测 (InputValidator)
  - 检测 NaN / Inf 值
  - 检测缺失必填字段
  - 检测空文本 / 极端分布
  - 异常时记录 MonitoringLog 并触发 fallback
  - **编写单元测试**: 各类异常输入检测、fallback 触发验证

- [x] **T-BE-003a** 实现告警生命周期管理 (NEW)
  - 告警状态机: TRIGGERED -> ACKNOWLEDGED -> RESOLVED -> CLOSED
  - 告警分级: CRITICAL / HIGH / MEDIUM / LOW
  - 通知渠道映射: CRITICAL(短信+邮件+站内信)、HIGH(邮件+站内信)、MEDIUM(站内信)、LOW(日报)
  - **编写单元测试**: 状态流转、通知发送、分级逻辑

### 2.2 灰度发布与回滚
- [x] **T-BE-004** 实现 CanaryManager 核心逻辑
  - 灰度比例配置 (1% / 5% / 25% / 50% / 100%)
  - 基于 `md5(user_id)[0:8] % 100 < traffic_percent` 的稳定哈希流量分配算法
  - 数据库动态配置，无需重启服务
  - 版本路由决策 (当前版本 vs 灰度版本)
  - **编写单元测试**: 流量分配均匀性、hash 一致性、动态配置生效

- [x] **T-BE-005** 实现自动回滚策略
  - 定义阈值: max_fallback_rate (默认 5%), max_drift_alerts_per_hour (默认 10), max_avg_latency_ms (默认 500)
  - 实现定时检查任务 (Celery beat 每 30s)
  - 自动回滚触发时: 切回基线 + 发送通知(站内信+邮件) + 记录原因
  - 人工回滚可覆盖自动回滚
  - **编写单元测试**: 阈值触发逻辑、回滚动作执行、通知发送验证

- [x] **T-BE-006** 实现 Canary API 路由
  - POST /canary/deployments (创建灰度)
  - PATCH /canary/deployments/{id}/traffic (调整流量)
  - POST /canary/deployments/{id}/rollback (回滚)
  - GET /canary/deployments (列表查询)
  - **编写单元测试**: CRUD 操作、状态流转、权限校验

### 2.3 真实样本验证
- [x] **T-BE-007** 实现离线验证引擎
  - 加载验证数据集 (CSV/JSON)
  - 批量推理并收集预测结果
  - 计算指标: Accuracy, Precision, Recall, F1, AUC, MAE, RMSE
  - 对比基线版本，计算 delta
  - **编写单元测试**: 指标计算正确性、对比逻辑

- [x] **T-BE-008** 实现 Validation API 路由
  - POST /validation/run (异步启动验证)
  - GET /validation/{id}/status (查询状态)
  - GET /validation/{id}/results (获取结果)
  - **编写单元测试**: 异步任务状态流转、结果格式

### 2.4 报告导出
- [x] **T-BE-009** 实现 PDF 报告生成服务
  - 后端使用 ReportLab 生成 PDF (主方案)
  - 支持用户风险报告 (含趋势图、建议)
  - 支持咨询师报告、管理分析报告
  - 小报告 (< 1000 条数据): 同步生成，时间 < 3s
  - 大报告 (>= 1000 条数据): Celery 异步生成，时间 < 30s
  - 生成后基础校验 (文件大小 > 0 / 页数 > 0 / 图表存在)
  - **编写单元测试**: PDF 生成成功、内容完整性、耗时检查、校验逻辑

- [x] **T-BE-010** 实现 Excel 批量导出服务
  - 使用 openpyxl 生成 .xlsx
  - 支持 10000+ 条数据导出
  - 支持列筛选和过滤条件
  - 流式写入防止内存溢出
  - **编写单元测试**: 大数据导出正确性、内存占用检查

- [x] **T-BE-011** 实现 Report API 路由
  - POST /reports/user-risk/pdf
  - POST /reports/batch-export/excel
  - GET /reports/templates (可用报告模板列表)
  - **编写单元测试**: 文件流响应、权限校验、错误处理

### 2.5 漂移检测边界修复
- [x] **T-BE-012** 修复漂移检测边界情况
  - 处理除零错误 (空分布 / 单值分布)
  - 处理极端分布 (所有值相同)
  - 添加 RuntimeWarning 捕获与处理
  - **编写单元测试**: 边界输入不抛异常、无 RuntimeWarning

---

## Phase 3: 前端功能 (Frontend)

### 3.1 前端性能优化
- [x] **T-FE-001** 实现路由懒加载
  - Vue Router 配置动态 import()
  - 按页面拆分 chunk (webpackChunkName)
  - 配置 optimizeDeps 预加载策略
  - **编写单元测试**: 路由懒加载生效、chunk 分离验证

- [x] **T-FE-002** 实现虚拟列表组件
  - 封装 VirtualList 组件 (基于固定高度)
  - 支持 1000+ 条数据流畅滚动
  - 滚动帧率 >= 50fps (使用 requestAnimationFrame 节流 + willChange: transform)
  - **编写单元测试**: 渲染节点数量、滚动事件处理 (8 组 28 个测试用例)

- [x] **T-FE-003** 实现图片懒加载
  - 封装 LazyImage 组件 (IntersectionObserver)
  - 支持占位图和加载动画
  - 内容区图片按需加载
  - **编写单元测试**: 视口进入时加载、占位图显示 (10 组 30 个测试用例)

- [x] **T-FE-004** 实现骨架屏组件
  - 封装 SkeletonScreen 组件
  - 覆盖 Dashboard / Risk / Monitoring 核心页面
  - 支持多种骨架布局 (列表/卡片/图表/统计/表格/自定义)
  - **编写单元测试**: 骨架屏渲染、数据加载后切换 (11 组 33 个测试用例)

- [x] **T-FE-005** 实现前端性能监控
  - 封装 usePerformanceMonitor composable
  - 采集 FCP, LCP, FID, CLS, TTFB + 自定义指标
  - 上报到后端 /monitoring/frontend-metrics (支持 fetch + Beacon API)
  - **编写单元测试**: 指标采集正确性、上报格式 (10 组 35 个测试用例)

- [x] **T-FE-005a** 实现错误页面 (NEW)
  - 创建 404 / 403 / 500 错误页面组件 (ErrorPage.vue + NotFoundPage.vue + ServerErrorPage.vue)
  - 支持返回首页和返回上一页操作
  - 错误页面支持 i18n 多语言
  - **编写单元测试**: 错误码匹配、页面渲染、i18n 切换 (8 组 24 个测试用例)

- [x] **T-FE-005b** 实现新页面 i18n 支持 (NEW)
  - 监控面板页面补充翻译键值 (zh-CN.ts + en-US.ts)
  - 报告中心页面补充翻译键值 (zh-CN.ts + en-US.ts)
  - 错误页面翻译键值补充
  - 延续 v1.3 vue-i18n 方案
  - **编写单元测试**: 中英文切换、键值完整性 (8 组 30 个测试用例)

### 3.2 数据可视化
- [x] **T-FE-006** 封装 ECharts 图表组件
  - 封装 BaseChart 组件 (支持响应式 + ResizeObserver)
  - 封装 RiskTrendChart (风险趋势曲线 + 上下限)
  - 封装 ModelPerformanceChart (模型性能对比柱状图)
  - 封装 SystemHealthChart (系统健康监控双 Y 轴)
  - 支持缩放、导出图片
  - **编写单元测试**: 图表渲染、响应式调整、导出功能 (8 组 32 个测试用例)

- [x] **T-FE-007** 实现监控面板页面
  - 创建 MonitoringDashboard 视图
  - 集成模型成功率、回退率、延迟统计卡片
  - 集成 SystemHealthChart + RiskTrendChart 图表
  - 集成漂移告警列表 (含严重级别/状态标签)
  - 支持时间范围切换 + 自动刷新 (5s)
  - 数据刷新延迟 < 5s
  - **编写单元测试**: 页面渲染、数据刷新、图表交互 (10 组 35 个测试用例)

### 3.3 报告中心
- [x] **T-FE-008** 实现报告中心页面
  - 创建 ReportCenter 视图
  - 支持 PDF 报告预览与下载
  - 支持 Excel 导出任务创建与下载
  - 显示导出历史记录 (含分页)
  - 支持导出状态标签、文件大小格式化
  - **编写单元测试**: 报告生成请求、下载触发、历史列表 (10 组 30 个测试用例)

---

## Phase 4: 测试体系增强 (QA Enhancement)

### 4.1 集成测试
- [x] **T-QA-001** 模型选择集成测试
  - 测试 CanaryManager 正确路由到不同版本
  - 测试灰度流量比例准确性 (1%, 5%, 10%, 25%, 50%, 75%, 100%)
  - 测试哈希一致性、分布均匀性、流量平滑增加
  - **验证标准**: 1000 次请求中灰度比例误差 < 1%

- [x] **T-QA-002** 融合逻辑集成测试
  - 测试多模型融合结果正确性 (加权平均/简单平均/多数投票)
  - 测试权重分配逻辑 (等权重/不等权重/极端权重)
  - 测试边界情况 (空输入/全零权重/单模型/多模型)
  - **验证标准**: 融合输出在预期范围内

- [x] **T-QA-003** 回退机制集成测试
  - 测试模型加载失败自动回退
  - 测试输入异常自动回退
  - 测试漂移告警触发回退
  - **验证标准**: 回退触发 < 200ms，回退结果正确

- [x] **T-QA-004** 灰度发布集成测试
  - 测试灰度创建 -> 扩量 -> 完成全流程
  - 测试自动回滚触发与执行
  - **验证标准**: 状态流转正确，日志完整

### 4.2 契约测试 (移至 v1.6)
> **⚠️ 说明**: 契约测试移至 v1.6 迭代

- [ ] **T-QA-005** API 契约测试 (v1.6)
  - 使用 schemathesis 测试所有 OpenAPI 端点
  - 验证输入输出字段结构稳定性
  - **验证标准**: 所有 API 通过契约测试

- [ ] **T-QA-006** 模型接口契约测试 (v1.6)
  - 验证模型输入特征字段一致性
  - 验证模型输出概率/标签格式
  - **验证标准**: 特征增删变动被捕获

### 4.3 异常输入测试
- [x] **T-QA-007** 空值与缺字段测试
  - 测试必填字段缺失时的响应
  - 测试 null / undefined 值处理
  - **验证标准**: 返回 400 错误，不触发 500
  - **测试文件**: `backend/tests/test_qa007_null_and_missing_fields.py` (16 个测试用例)

- [x] **T-QA-008** 非法类型与极端分布测试
  - 测试字符串传入数字字段
  - 测试极大/极小数值
  - 测试数组长度超限
  - **验证标准**: 优雅降级，记录异常日志
  - **测试文件**: `backend/tests/test_qa008_invalid_types_and_extreme_distributions.py` (17 个测试用例)

### 4.4 性能回归测试
- [x] **T-QA-009** 推理耗时性能测试
  - 基线: 单条推理 < 200ms (P99)
  - 批量推理 100 条 < 5s
  - **验证标准**: 不劣于 v1.4 基线
  - **测试文件**: `backend/tests/test_qa009_inference_performance.py` (10 个测试用例)

- [x] **T-QA-010** 前端加载性能测试
  - 基线: 首屏 FCP < 2.5s, LCP < 4.0s
  - 长列表滚动帧率 >= 50fps
  - **验证标准**: 首屏加载时间降低 30%
  - **测试文件**: `frontend/src/composables/usePerformanceMonitor.test.ts` (16 个测试用例)

- [x] **T-QA-011** 资源占用性能测试
  - 内存占用增长 < 10% (相比 v1.4)
  - CPU 使用率峰值 < 80%
  - **验证标准**: 无内存泄漏
  - **测试文件**: `backend/tests/test_qa011_resource_usage.py` (9 个测试用例)

---

## Phase 5: 回退与容错验证 (Fallback & Resilience)

- [x] **T-RES-001** 模型加载失败回退验证
  - 删除/损坏模型文件，验证自动回退到启发式规则
  - **验证标准**: 回退触发，用户无感知，日志记录完整
  - **测试文件**: `backend/tests/test_resilience_phase5.py` (T-RES-001 相关 3 个测试用例)

- [x] **T-RES-002** 依赖缺失回退验证
  - 在无 PyTorch 环境中启动，验证回退行为
  - **验证标准**: 系统正常启动，torch 模型自动回退
  - **测试文件**: `backend/tests/test_resilience_phase5.py` (T-RES-002 相关 3 个测试用例)

- [x] **T-RES-003** 预测异常回退验证
  - 注入 NaN / Inf 预测结果
  - 注入超出范围的预测概率
  - **验证标准**: 自动回退，返回有效结果
  - **测试文件**: `backend/tests/test_resilience_phase5.py` (T-RES-003 相关 4 个测试用例)

- [x] **T-RES-004** 延迟超时回退验证
  - 模拟推理延迟 > 200ms
  - **验证标准**: 触发超时告警并回退
  - **测试文件**: `backend/tests/test_resilience_phase5.py` (T-RES-004 相关 3 个测试用例)

## Phase 6: 文档更新 (Documentation)

- [x] **T-DOC-001** 更新 API 文档
  - 补充 /monitoring, /canary, /validation, /reports 接口说明 (16 个接口)
  - 包含请求/响应示例、错误码表
  - **审核**: 与后端路由实现一致

- [x] **T-DOC-002** 更新 CHANGELOG
  - 记录 v1.5 所有功能变更 (后端/前端/测试/文档)
  - 包含历史版本变更记录

- [x] **T-DOC-003** 编写部署指南
  - 包含环境要求、部署步骤
  - 包含灰度发布流程和 API 示例
  - 包含监控告警配置、性能基准
  - 包含故障排查和回滚策略

---

## 任务统计

| Phase | 任务数 | 状态 |
|-------|--------|------|
| Phase 1: 基础设施 | 7 | 7/7 ✅ |
| Phase 2: 后端核心 | 13 | 13/13 ✅ |
| Phase 3: 前端功能 | 10 | 10/10 ✅ |
| Phase 4: 测试增强 | 7 | 7/7 ✅ |
| Phase 5: 回退验证 | 4 | 4/4 ✅ |
| Phase 6: 文档更新 | 3 | 3/3 ✅ |
| **总计** | **44** | **44/44 ✅** |

> **说明**: T-QA-005/T-QA-006 (契约测试) 已移至 v1.6 迭代，不计入当前迭代任务统计。

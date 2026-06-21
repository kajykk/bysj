# 变更日志

所有项目的显著变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [1.5.0] - 2024-01-15

### 新增 - 性能监控与可观测性

#### 后端

- **监控指标采集**
  - 新增 `ObservabilityService` 服务，支持模型成功率、回退率、延迟等指标采集
  - 新增 `/monitoring/metrics` API 端点，支持实时和历史指标查询
  - 新增前端性能指标上报端点 `/monitoring/frontend-metrics`
  - 支持 Core Web Vitals (FCP, LCP, FID, CLS, TTFB) 采集

- **灰度发布管理**
  - 新增 `CanaryManager` 服务，支持完整的灰度发布生命周期管理
  - 新增 `/canary/deployments` API 端点，支持创建、查询、调整、回滚灰度发布
  - 支持基于用户 ID 哈希的稳定流量分割
  - 支持自动回滚（成功率 < 98% 触发）

- **离线验证引擎**
  - 新增 `ValidationEngine` 服务，支持模型离线性能评估
  - 新增 `/validation/tasks` API 端点，支持创建验证任务和查询结果
  - 支持数据漂移检测（PSI、KL 散度）
  - 支持混淆矩阵、校准曲线生成

- **报告导出服务**
  - 新增 `PDFReportService` 服务，支持用户风险报告 PDF 生成
  - 新增 `ExcelExportService` 服务，支持咨询师报告 Excel 导出
  - 新增 `/reports/pdf` 和 `/reports/excel` API 端点
  - 支持异步导出任务和下载历史记录

#### 前端

- **性能优化组件**
  - 新增 `VirtualList` 虚拟列表组件，支持 1000+ 条数据流畅滚动
  - 新增 `LazyImage` 图片懒加载组件，基于 IntersectionObserver
  - 新增 `SkeletonScreen` 骨架屏组件，支持列表/卡片/图表/统计/表格变体

- **监控与报告页面**
  - 新增 `MonitoringDashboard` 监控面板页面，集成实时指标图表
  - 新增 `ReportCenter` 报告中心页面，支持 PDF/Excel 导出
  - 新增 `SystemHealthChart`、`RiskTrendChart`、`ModelPerformanceChart` 图表组件

- **错误处理与国际化**
  - 新增 `ErrorPage` 错误页面组件，支持 404/403/500 状态码
  - 新增 `NotFoundPage`、`ServerErrorPage` 视图
  - 补充监控面板和报告中心页面的 i18n 翻译键值（中英文）

- **性能监控**
  - 新增 `usePerformanceMonitor` composable，自动采集性能指标
  - 支持 fetch + Beacon API 双模式上报

#### 测试

- **集成测试**
  - 新增灰度路由集成测试 (`test_canary_routing.py`)，验证流量分割准确性
  - 新增融合逻辑集成测试 (`test_fusion_logic.py`)，验证多模型融合正确性
  - 新增回退机制集成测试 (`test_fallback_mechanism.py`)，验证模型失败回退
  - 新增灰度发布集成测试 (`test_canary_deployment.py`)，验证完整发布流程

#### 文档

- 新增 v1.5 API 文档，包含 16 个接口的详细说明
- 新增部署指南和性能基准测试报告

---

## [1.4.0] - 2023-12-01

### 新增 - 深度学习模型转换

- XGBoost/LightGBM 模型转换为 PyTorch MLP
- 模型融合策略（加权平均/简单平均/多数投票）
- 模型版本管理与 A/B 测试支持

---

## [1.3.0] - 2023-10-15

### 新增 - 移动端适配与国际化

- 移动端响应式布局适配
- 深色模式支持
- 国际化 (i18n) 支持（中文/英文）

---

## [1.2.0] - 2023-09-01

### 新增 - 前端性能优化

- 路由懒加载与代码分割
- Element Plus 组件按需加载
- 前端资源压缩与缓存策略

---

## [1.1.0] - 2023-08-01

### 新增 - 生理信号优化

- 生理信号特征工程优化
- 心率变异性 (HRV) 分析
- 多模态数据融合

---

## [1.0.0] - 2023-07-01

### 初始版本

- 用户风险评估系统基础架构
- 基于 XGBoost 的心理健康风险预测模型
- 前端 Vue 3 + Element Plus 管理后台
- 基础用户管理和权限系统

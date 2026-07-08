# 前后端一致性对齐：前端功能页面设计

- **日期**: 2026-07-08
- **状态**: 已修订 v3（通过 `md/17.md` 审阅，5 必须 + 5 建议全部落实），可进入实现计划
- **范围**: 为后端已实现但前端缺失的 4 个 API 域补齐前端页面与 API 客户端
- **原则**: 不改后端；遵循现有 Vue 3 + TS + Element Plus 模式；YAGNI
- **v3 修订要点**: ①reportsApi 补 `getUserRiskReport/getUserRiskTrend` ②JSON 导出行为明确（后端 ok()，前端构造 .json Blob）③E2E 文案修正（4 新页 + 1 补齐）④i18n 导航补齐项核查说明 ⑤PDF 表单以 `UserRiskReportRequest` schema 为准（user_id 必填已核实）⑥observabilityApi query 类型说明 ⑦monitoring 单块降级 ⑧批量 Excel 大小限制 ⑨routeAccess 引用方式统一 ⑩ROLE_PERMISSIONS 允许重复不去重

## 1. 背景与差距

后端 `/api/v1` 下有 6 个域完全缺失前端页面/API 客户端。经确认，本次覆盖 4 个域：

| 域 | 后端端点前缀 | 前端现状 |
|----|--------------|----------|
| 报告中心 | `/reports/*` + `/user/risk/export` | 完全缺失 |
| 可观测性 | `/alerts/observability/*` | 完全缺失 |
| 系统监控 | `/monitoring/*` | 完全缺失 |
| 金丝雀管理 | `/canary/*` | 完全缺失 |

不在本次范围：模型校验 (`/validation/*`)、Grafana 适配器 (`/alerts/observability/grafana/*`，是数据源插件非页面)。

## 2. 权限模型（关键约束）

后端权限校验分两类机制，前端 `ROLE_PERMISSIONS` (`frontend/src/config/permissions.ts`) 须分别对齐：

- **user** 角色拥有 `user.export.risk` → 可访问 `GET /user/risk/export?format=pdf|csv|json&days=N`（流式下载自己的风险数据）。后端 `user_risk.py` 用 `require_permission("user.export.risk")`。
- **admin** 角色拥有 `admin.predict.audit` → 可访问全部 `/reports/*` 与 `/canary/*`。后端这两域用 `require_permission("admin.predict.audit")`。
- **`/monitoring/*`** 后端用 `require_permission("admin.predict.audit")`（6 个端点），仅 `dashboard-summary` 用 `admin.dashboard.view`。因此前端页面权限取 `admin.predict.audit`（覆盖绝大多数端点）。
- **`/alerts/observability/*`** 后端用 **`require_role("admin")`**（角色级校验，非 permission matrix，见 `observability/__init__.py` 的 `AdminDep`）。前端仍用 `admin.alerts.view` 作为**页面访问粒度**（该权限仅授予 admin），保持前端导航/菜单权限体系一致；这不是后端 PERMISSION_MATRIX 直接控制，而是前端菜单粒度。

结论：报告中心必须按角色拆分——用户侧用 `/user/risk/export`，管理员侧用 `/reports/*`。二者权限不同，不可共用端点。

## 3. 页面组织决策

3 个管理员域（可观测性/系统监控/金丝雀）采用**独立页面**而非合并：

- 可观测性主题是**告警系统**运维（告警趋势/响应时长/升级/通道/静默命中率）
- 系统监控主题是 **ML 模型健康**（模型成功率/回退/漂移/引擎快照）
- 金丝雀有写操作（部署/流量/暂停/恢复/回滚/完成），必须独立

合并会混淆数据源与刷新策略，独立页符合现有「一路由一页」模式。

## 4. 新增页面设计（5 个）

### 4.1 用户报告中心 `/user/reports` — `UserReportsPage.vue`

- **角色/权限**: user / `user.export.risk`
- **后端端点**:
  - `GET /user/risk/report` — 风险摘要（等级/评分/趋势/主要因子/建议）
  - `GET /user/risk/trend?days=N` — 风险趋势点序列
  - `GET /user/risk/export?format=pdf|csv|json&days=N` — pdf/csv 为 StreamingResponse，json 为 ApiResponse（见导出实现）
- **布局**:
  - 顶部：风险摘要卡（当前等级徽标 + 评分 + 趋势方向 + 评估时间）
  - 中部：时间范围选择器（7/30/90/365 天，对齐后端 `days` Query ge=1 le=365）+ 风险趋势折线图（复用 `BaseChart`/`useECharts`）
  - 底部：导出按钮组（PDF / CSV / JSON 三个按钮），三按钮体验一致均触发浏览器下载
- **导出实现**（后端 `user_risk.py` export_risk 已核实）:
  - `format=pdf|csv` → 后端返回 `StreamingResponse`，前端 `responseType: 'blob'` 接收后 `URL.createObjectURL` 触发下载，文件名从 `Content-Disposition` 解析
  - `format=json` → 后端返回 `ok(data)`（**ApiResponse 包裹，非流式**），前端用 `requestData` 取数据后**自行构造 `application/json` Blob** 触发 `risk-report.json` 下载（保持三按钮体验一致，不误认为后端 JSON 也是 StreamingResponse）
- **错误处理**: 导出失败用 `httpFeedback` 统一提示（注：`/user/risk/export` 后端未挂限流器，无需处理 429）

### 4.2 管理员报告中心 `/admin/reports` — `AdminReportsPage.vue`

- **角色/权限**: admin / `admin.predict.audit`
- **后端端点**:
  - `GET /reports/templates` — 4 个内置模板（user-risk/counselor-summary/management-analysis/batch-export）
  - `POST /reports/user-risk/pdf` — 同步生成 PDF（StreamingResponse）
  - `POST /reports/user-risk/pdf/async` — 异步生成，返回 `job_id`
  - `GET /reports/pdf/{job_id}/status` — 轮询任务状态（queued/running/completed/failed + progress）
  - `GET /reports/pdf/{job_id}/download` — 下载已完成 PDF
  - `GET /reports/pdf/jobs` — 任务列表
  - `POST /reports/batch-export/excel` — 批量 Excel 导出（StreamingResponse）
  - （celery 变体 `/reports/user-risk/pdf/celery-async` + `/reports/pdf/celery/{job_id}/status|download`：**仅 API 客户端接通 + 单测覆盖，第一版页面不暴露 celery 专用入口**。因 celery fallback 回到 in-process `pdf_job_store`，任务存储后端不统一，UI 不主动区分，避免任务列表语义混乱）
- **布局**（三分区）:
  1. **报告模板区**: `GET /reports/templates` 渲染 4 个模板卡片（名称/描述/格式/所需权限）
  2. **生成 PDF 区**: 表单字段**以 `backend/app/schemas/reports.py` 的 `UserRiskReportRequest` 为准**（已核实：`user_id`(必填) + `user_name` + `risk_level` + `risk_trend` + `recommendations`）+ 两个按钮「同步生成」「异步生成」。异步生成后展示 job_id 与进度条，每 2s 轮询 `GET /reports/pdf/{job_id}/status`，completed 后启用「下载」按钮调用 `GET /reports/pdf/{job_id}/download`
  3. **任务列表 + 批量导出区**: `GET /reports/pdf/jobs` 表格（job_id/用户/状态/进度/创建时间/下载）；批量 Excel 导出表单（data 数组 + columns + filters + filename）→ `POST /reports/batch-export/excel` 流式下载。第一版 `data` 用 JSON 输入框 + 校验（手填数组体验差，后续再接数据选择器）。**前端限制**：data 最大 1000 行、columns 最大 50 列、单元格文本长度提示、JSON parse 失败不提交（后端已有校验，前端给更好体验）
- **限流**: 同步 PDF 5/min、异步 10/min、任务列表 30/min，超限提示
- **轮询控制**: 组件卸载时清理定时器；任务终态（completed/failed）停止轮询

### 4.3 可观测性仪表盘 `/admin/observability` — `AdminObservabilityPage.vue`

- **角色/权限**: admin / `admin.alerts.view`
- **后端端点**（8 个 GET，均支持 `start_time`/`end_time` Query，最大跨度 30 天，默认 24h）:
  - `GET /alerts/observability/health` — 系统健康
  - `GET /alerts/observability/trend` — 告警趋势
  - `GET /alerts/observability/response-time` — 响应时长
  - `GET /alerts/observability/escalation` — 升级率
  - `GET /alerts/observability/channel-stats` — 通道成功率
  - `GET /alerts/observability/silence-hit-rate` — 静默命中率
  - `GET /alerts/observability/am-sync` — AM 同步状态
  - `GET /alerts/observability/lock-stats` — Redis 锁统计
- **布局**: 顶部时间范围选择器（默认 24h，最大 30 天，对齐 `MAX_TIME_RANGE_DAYS=30`）+ 8 个指标区块网格。每个区块独立加载（`Promise.allSettled` 并发）、独立错误降级（单块失败不影响其他）
- **刷新**: 手动刷新按钮 + 可选 60s 自动刷新开关（后端已 5min Redis 缓存，前端不必高频）
- **可视化**: 趋势用折线图，通道成功率/静默命中率用仪表盘或进度条，其余用数值卡 + 状态标签

### 4.4 系统监控 `/admin/monitoring` — `AdminMonitoringPage.vue`

- **角色/权限**: admin / `admin.predict.audit`（后端 6/7 端点用此权限；仅 `dashboard-summary` 用 `admin.dashboard.view`，admin 角色两者皆有）
- **后端端点**（7 个 GET，跳过 `POST /monitoring/frontend-metrics` 因其由 `usePerformanceMonitor` 自动上报）:
  - `GET /monitoring/dashboard-summary` — 摘要卡
  - `GET /monitoring/model-success-rate` — 模型成功率
  - `GET /monitoring/fallback-stats` — 回退统计
  - `GET /monitoring/drift-alerts` — 漂移告警列表
  - `GET /monitoring/engine-snapshot` — 引擎快照
  - `GET /monitoring/request-details` — 请求详情列表（分页）
  - `GET /monitoring/request-details/{log_id}` — 单条请求详情
- **布局**: 顶部摘要卡（`dashboard-summary`）+ 模型成功率折线 + 回退统计柱状 + 漂移告警列表 + 引擎快照面板 + 请求详情表格（分页，点击行展开 `request-details/{log_id}`）。请求详情可能含输入文本等敏感字段，展示时脱敏（截断/掩码）
- **局部降级**: 各区块（dashboard-summary / model-success-rate / fallback-stats / drift-alerts / engine-snapshot / request-details）**独立加载**（`Promise.allSettled`），单块失败（含 `dashboard-summary` 因 `admin.dashboard.view` 缺失 403）只影响对应区块，不白屏
- **刷新**: 顶部 30s 自动刷新开关 + 手动刷新

### 4.5 金丝雀管理 `/admin/canary` — `AdminCanaryPage.vue`

- **角色/权限**: admin / `admin.predict.audit`
- **后端端点**（9 个）:
  - `GET /canary/deployments` — 部署列表
  - `GET /canary/deployments/{id}` — 部署详情
  - `POST /canary/deployments` — 新建（version + traffic_percent + thresholds）
  - `PATCH /canary/deployments/{id}/traffic` — 调整流量
  - `POST /canary/deployments/{id}/pause` — 暂停
  - `POST /canary/deployments/{id}/resume` — 恢复
  - `POST /canary/deployments/{id}/rollback` — 回滚（需 reason）
  - `POST /canary/deployments/{id}/complete` — 完成
  - `GET /canary/traffic-percentages` — **可选流量百分比选项**（后端 docstring `Get available traffic percentage options`，返回 `{percentages: [...]}`），非当前实际流量分配
- **布局**: 顶部当前部署状态摘要（从 `deployments` 列表按 status 聚合，如 running/paused/completed 计数）+ 可选流量百分比提示（`traffic-percentages` 仅作新建/调整时滑块刻度参考）+ 部署列表表格（版本/流量%/状态/起始时间/操作）。新建部署对话框。行内操作按钮：调整流量（滑块，刻度取自 `traffic-percentages`）、暂停/恢复、回滚（二次确认 + reason 输入）、完成
- **状态机**: 状态字段 `status` 驱动按钮可用性（如 running 才能 pause/rollback，paused 才能 resume）
- **写操作安全**: 回滚/完成用 danger 类型 + 二次确认；写操作成功后刷新 deployments 列表与状态摘要；新建/调整流量时若有 active/running 部署需冲突提示
- **限流**: 10/min 创建、30/min 查询

## 5. API 客户端设计（4 个新文件）

所有文件遵循现有模式：`import request, { requestData } from './request'` + 强类型 interface + 导出聚合对象。

### 5.0 响应解包约定（关键）

后端响应分三类，前端必须分别处理，不能统一用 `requestData`：

1. **`ApiResponse` 包裹**（后端 `ok()` 返回，`response_model=ApiResponse`）：用 `requestData<T>()`，T 为 `data` 内层。适用于 `/reports/*`、`/canary/*`、`/user/risk/*`。
2. **`StreamingResponse`**（PDF/Excel/CSV 下载）：用 `request.get/post(..., { responseType: 'blob' })` 返回 `Blob`，文件名从 `Content-Disposition` 解析，解析失败用 fallback（如 `risk-report.pdf`）。
3. **裸 dict**（observability 用 `response_model=dict` + `with_instance_meta`，返回 `{data, instance_id, cached, generated_at}`）：**不**用 `requestData`（会丢失 cached/instance_id 元信息）。用 `request.get<ObservabilityEnvelope<T>>().then(res => res.data)`，保留 envelope，页面可显示「缓存命中」标识。payload 在 `res.data.data`。

### 5.1 `src/api/reportsApi.ts`

用户导出**拆为独立函数**避免 `Blob | Json` 联合类型污染调用方：

```ts
// 用户侧（user.export.risk）—— 摘要/趋势 + 拆三个导出函数，类型安全
getUserRiskReport: () => requestData<UserRiskReport>                    // GET /user/risk/report
getUserRiskTrend: (days = 30) => requestData<UserRiskTrend>             // GET /user/risk/trend?days=N
exportUserRiskPdf(days = 90): Promise<Blob>      // GET /user/risk/export?format=pdf  responseType:'blob'
exportUserRiskCsv(days = 90): Promise<Blob>      // GET /user/risk/export?format=csv  responseType:'blob'
exportUserRiskJson(days = 90): Promise<UserRiskExportJson>  // GET /user/risk/export?format=json  requestData（后端 ok() 包裹）→ 前端构造 .json Blob 下载

// 管理员侧（admin.predict.audit）—— 均为 ApiResponse 包裹，用 requestData
listReportTemplates: () => requestData<{ templates: ReportTemplate[]; total: number }>
generateUserRiskPdfSync: (payload: UserRiskReportRequest) => Promise<Blob>   // StreamingResponse → blob
generateUserRiskPdfAsync: (payload: UserRiskReportRequest) => requestData<{ job_id: string; status: string; message: string }>
getPdfJobStatus: (jobId: string) => requestData<PdfJobStatus>
downloadPdf: (jobId: string) => Promise<Blob>                                 // StreamingResponse → blob
listPdfJobs: () => requestData<{ jobs: PdfJobItem[]; total: number }>          // 注意非标准分页，用 requestData 非 requestPageData
batchExportExcel: (payload: BatchExportRequest) => Promise<Blob>              // StreamingResponse → blob

// celery 异步变体：仅在 API 客户端接通并单测覆盖；第一版页面不暴露 celery 专用入口
// （celery fallback 时后端返回 backend:"thread-fallback" 并提示轮询 /reports/pdf/{job_id}/status，
//  任务存储与 in-process pdf_job_store 不统一，UI 不主动区分，避免任务列表语义混乱）
generateUserRiskPdfCeleryAsync: (payload: UserRiskReportRequest) => requestData<{ job_id: string; status: string; message: string; backend?: string }>
getCeleryPdfJobStatus: (jobId: string) => requestData<PdfJobStatus>
downloadCeleryPdf: (jobId: string) => Promise<Blob>
```

### 5.2 `src/api/observabilityApi.ts`

8 个 GET 函数，统一接收基础时间范围 `{ start_time?: string; end_time?: string }`，按端点扩展额外 query（如 trend 支持 `bucket/severity/status/group_by`）。返回 `ObservabilityEnvelope<T>`（含 `data/instance_id/cached/generated_at`）：

```ts
interface ObservabilityEnvelope<T> { data: T; instance_id: string; cached: boolean; generated_at: string }
interface ObservabilityTimeRange { start_time?: string; end_time?: string }
// 第一版可用宽 query 类型（ObservabilityTimeRange + 可选扩展字段），但 API 单测必须覆盖每个端点实际传参，
// 避免页面传入后端不支持的 query。若需更严谨可按端点拆 interface（AlertTrendQuery 等）。
// 用 request.get<ObservabilityEnvelope<T>>(url, { params }).then(res => res.data)，保留 cached 元信息
getHealth / getTrend / getResponseTime / getEscalation /
getChannelStats / getSilenceHitRate / getAmSync / getLockStats
```

### 5.3 `src/api/monitoringApi.ts`

7 个 GET 函数。后端 `response_model=ApiResponse`（用 `ok()`），故用 `requestData<T>`：

```ts
getDashboardSummary / getModelSuccessRate / getFallbackStats /
getDriftAlerts / getEngineSnapshot /
getRequestDetailsList(query) / getRequestDetail(logId)
// request-details 若为分页需先确认其结构是否为 {items,total,page,page_size}；
// 若不是（如 {items,total}），用 requestData 而非 requestPageData
```

### 5.4 `src/api/canaryApi.ts`

后端用 `ok()`（ApiResponse 包裹）。**注意 `CanaryListResponse = {total, limit, offset, items}` 非 `{items,total,page,page_size}`，不能用 `requestPageData`**，用 `requestData<CanaryListResponse>`：

```ts
listCanaryDeployments: () => requestData<CanaryListResponse>   // {total, limit, offset, items}
getCanaryDeployment: (id) => requestData<CanaryDeploymentResponse>
createCanaryDeployment: (payload: CanaryCreateRequest) => requestData<CanaryDeploymentResponse>
updateCanaryTraffic: (id, payload: CanaryTrafficUpdateRequest) => requestData<CanaryDeploymentResponse>
pauseCanary / resumeCanary / completeCanary: (id) => requestData<CanaryDeploymentResponse>
rollbackCanary: (id, payload: CanaryRollbackRequest) => requestData<CanaryDeploymentResponse>
getCanaryTrafficPercentages: () => requestData<{ percentages: number[] }>   // 可选项，非当前分配
```

### 5.5 导出聚合

在 `src/api/index.ts` 追加：

```ts
export { reportsApi } from './reportsApi'
export { observabilityApi } from './observabilityApi'
export { monitoringApi } from './monitoringApi'
export { canaryApi } from './canaryApi'
```

## 6. 路由与导航变更

### 6.1 路由新增（`frontend/src/router/index.ts`，MainLayout children）

| path | name | component | meta |
|------|------|-----------|------|
| `user/reports` | - | `@/views/user/UserReportsPage.vue` | `{ role: 'user', permissions: ['user.export.risk'], title: 'nav.user.reports' }` |
| `admin/reports` | - | `@/views/admin/AdminReportsPage.vue` | `{ role: 'admin', permissions: ['admin.predict.audit'], title: 'nav.admin.reports' }` |
| `admin/observability` | - | `@/views/admin/AdminObservabilityPage.vue` | `{ role: 'admin', permissions: ['admin.alerts.view'], title: 'nav.admin.observability' }` |
| `admin/monitoring` | - | `@/views/admin/AdminMonitoringPage.vue` | `{ role: 'admin', permissions: ['admin.predict.audit'], title: 'nav.admin.monitoring' }` |
| `admin/canary` | - | `@/views/admin/AdminCanaryPage.vue` | `{ role: 'admin', permissions: ['admin.predict.audit'], title: 'nav.admin.canary' }` |

### 6.2 菜单挂载（`frontend/src/layouts/MainLayout.vue` roleMenus）

**新增页面菜单（5 项）**：
- **user** 菜单末尾插入：`{ titleKey: 'nav.user.reports', path: '/user/reports', icon: Document }`
- **admin** 菜单末尾插入 4 项：reports（Document）、observability（DataLine）、monitoring（Monitor）、canary（Promotion）

**附带导航一致性补齐（2 项，不新建页面，仅补已存在路由的菜单入口）**：
- **counselor** 菜单补「审核列表」：`{ titleKey: 'nav.counselor.reviews', path: '/counselor/reviews', icon: ChatLineRound }`（`CounselorReviewListPage.vue` 已存在，仅菜单缺失）
- **admin** 菜单补「危机事件」：`{ titleKey: 'nav.admin.crisisEvents', path: '/admin/crisis-events', icon: Warning }`（`AdminCrisisEventsPage.vue` 已存在，仅菜单缺失）

## 7. 权限与 i18n 配套

### 7.1 `frontend/src/config/permissions.ts`

- `PAGE_PERMISSIONS` 新增：
  - `userReports: ['user.export.risk']`
  - `adminReports: ['admin.predict.audit']`
  - `adminObservability: ['admin.alerts.view']`（前端菜单粒度；后端为 `require_role("admin")`）
  - `adminMonitoring: ['admin.predict.audit']`（后端 6/7 端点用此权限）
  - `adminCanary: ['admin.predict.audit']`
- **`PermissionKey` 联合类型无需新增**：本次使用的权限字符串（`user.export.risk`、`admin.predict.audit`、`admin.alerts.view`）均已存在于 `frontend/src/types/permission.ts`，不要误加 `admin.monitoring.view` 等新字符串以免与后端不一致。
- **`ROLE_PERMISSIONS.admin` 显式展开新 PAGE_PERMISSIONS**：不要仅依赖 `adminAlerts`/`admin.predict.audit` 的现有副作用。将 `...PAGE_PERMISSIONS.adminReports, ...PAGE_PERMISSIONS.adminObservability, ...PAGE_PERMISSIONS.adminMonitoring, ...PAGE_PERMISSIONS.adminCanary` 显式追加到 `ROLE_PERMISSIONS.admin` 数组，避免未来 `adminAlerts` 拆分时 `admin.alerts.view` 被移除导致可观测性页失权。**允许权限字符串重复**（如 `admin.predict.audit` 多次出现），`includes()` 判断不受影响；本次不引入去重重构。
- `ROLE_PERMISSIONS.user` 已含 `user.export.risk`（追加 `...PAGE_PERMISSIONS.userReports` 显式化）。

### 7.2 `frontend/src/config/routeAccess.ts`

`ROUTE_PERMISSIONS` 新增对应键：`userReports`、`adminReports`、`adminObservability`、`adminMonitoring`、`adminCanary`。router meta 优先引用常量 `permissions: ROUTE_PERMISSIONS.adminReports`（减少重复、保持单一数据源）；若现有路由习惯用数组字面量，则两者值必须一致。实现前先核对 `router/index.ts` 现有写法并遵循之。

### 7.3 i18n（`frontend/src/i18n/locales/zh-CN.ts` 与 `en-US.ts`）

新增 nav 键：`nav.user.reports`、`nav.admin.reports`、`nav.admin.observability`、`nav.admin.monitoring`、`nav.admin.canary`，以及各页面内文案键（标题/按钮/表单标签/状态枚举）。**导航补齐项** `nav.counselor.reviews`、`nav.admin.crisisEvents`：若 i18n 已存在则复用，若缺失需同步补充 zh-CN/en-US（实现前先 grep 确认）。

## 8. 测试策略

- **API 客户端单测**: 每个新 `*Api.ts` 配套 `.test.ts`，沿用 `base.test.ts`/`request.test.ts` 的 mock 模式，覆盖 URL/方法/参数/blob 返回；observability 单测须验证保留 envelope（cached/instance_id）；canary 单测验证用 `requestData` 而非 `requestPageData`
- **路由守卫**: `routeAccess.test.ts` 补 5 条新路由的权限判定用例（含 monitoring 用 `admin.predict.audit`）
- **页面冒烟**: 每个新页面配套 `.test.ts`，覆盖挂载、权限缺失重定向、关键交互（导出触发/轮询启停/确认对话框）
- **轻量 E2E smoke（新增 1 条）**: 用 Playwright 覆盖菜单/路由/权限边界可达性，不涉及复杂交互：
  1. admin 登录 → 验证菜单出现「报告中心/可观测性/系统监控/金丝雀管理/危机事件」5 项
  2. 逐个进入 **4 个新 admin 页面**（reports/observability/monitoring/canary）+ **1 个导航补齐页面**（crisis-events），验证页面标题与主容器存在
  3. user 登录 → 验证「报告中心」入口出现，访问 `/admin/*` 被拒绝/重定向

## 9. 不做的事（YAGNI）

- 不改后端任何代码
- 不做模型校验页（`/validation/*`）
- 不重构现有页面
- 不为金丝雀/可观测性加 WebSocket 实时推送（用轮询/手动刷新）
- 不嵌入 Grafana（`/alerts/observability/grafana/*` 是数据源适配器）
- 不新增 celery 异步 PDF 的页面入口（仅 API 客户端接通 + 单测；第一版 UI 只用 in-process async + 任务列表）

## 10. 交付物清单

```
frontend/src/api/
  reportsApi.ts + reportsApi.test.ts
  observabilityApi.ts + observabilityApi.test.ts
  monitoringApi.ts + monitoringApi.test.ts
  canaryApi.ts + canaryApi.test.ts
  index.ts (追加导出)
frontend/src/views/
  user/UserReportsPage.vue + UserReportsPage.test.ts
  admin/AdminReportsPage.vue + AdminReportsPage.test.ts
  admin/AdminObservabilityPage.vue + AdminObservabilityPage.test.ts
  admin/AdminMonitoringPage.vue + AdminMonitoringPage.test.ts
  admin/AdminCanaryPage.vue + AdminCanaryPage.test.ts
frontend/src/router/index.ts (追加 5 路由)
frontend/src/layouts/MainLayout.vue (菜单追加 5 新页 + 2 导航补齐)
frontend/src/config/permissions.ts (PAGE_PERMISSIONS 追加 5 键 + ROLE_PERMISSIONS 显式展开)
frontend/src/config/routeAccess.ts (ROUTE_PERMISSIONS 追加 5 键)
frontend/src/i18n/locales/zh-CN.ts + en-US.ts (nav + 文案)
frontend/e2e/ (新增 1 条轻量 smoke：菜单/路由/权限可达性)
```

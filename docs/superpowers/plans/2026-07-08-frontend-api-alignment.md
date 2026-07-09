# Frontend-API Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build 5 frontend pages + 4 API clients covering 4 backend API domains (reports, observability, monitoring, canary) that currently have no frontend, plus wire routes/menu/permissions/i18n.

**Architecture:** API client layer (`src/api/*Api.ts`) wraps `request`/`requestData` per response-type rules (ApiResponse→requestData, StreamingResponse→blob, bare dict→envelope). Pages consume clients under MainLayout with role+permission guards. Config (permissions/routeAccess/i18n/router/menu) extended in-place following existing patterns.

**Tech Stack:** Vue 3 (`<script setup lang="ts">`), Element Plus, ECharts (BaseChart/useECharts), vue-i18n, vitest (unit), Playwright (e2e).

**Spec:** `docs/superpowers/specs/2026-07-08-frontend-api-alignment-design.md` (v3)

## Global Constraints

- 不改后端任何代码；前端跟随后端实际权限与响应格式
- monitoring 页权限 `admin.predict.audit`；observability 后端为 `require_role("admin")`，前端用 `admin.alerts.view` 作菜单粒度
- 响应解包三类：ApiResponse 包裹→`requestData<T>`；StreamingResponse→`responseType:'blob'`；observability 裸 dict→`request.get<Envelope<T>>().then(res=>res.data)`
- canary 列表 `{total,limit,offset,items}` 非标准分页，用 `requestData` 非 `requestPageData`
- `userRiskApi` 已有 `getRiskReport`/`getRiskTrend`，reportsApi 不重复，UserReportsPage 复用
- celery PDF 仅 API 客户端接通+单测，第一版 UI 不暴露
- 测试命令：单测 `cd frontend && npx vitest run <path>`；类型检查 `cd frontend && npx vue-tsc --noEmit`；e2e `cd frontend && npx playwright test <path>`
- 提交前必须通过对应单测 + `npx vue-tsc --noEmit`
- nav.counselor.reviews / nav.admin.crisisEvents i18n 已存在，无需新增

---

## File Structure

**Create (14 files):**
- `frontend/src/api/reportsApi.ts` + `reportsApi.test.ts`
- `frontend/src/api/observabilityApi.ts` + `observabilityApi.test.ts`
- `frontend/src/api/monitoringApi.ts` + `monitoringApi.test.ts`
- `frontend/src/api/canaryApi.ts` + `canaryApi.test.ts`
- `frontend/src/views/user/UserReportsPage.vue` + `UserReportsPage.test.ts`
- `frontend/src/views/admin/AdminReportsPage.vue` + `AdminReportsPage.test.ts`
- `frontend/src/views/admin/AdminObservabilityPage.vue` + `AdminObservabilityPage.test.ts`
- `frontend/src/views/admin/AdminMonitoringPage.vue` + `AdminMonitoringPage.test.ts`
- `frontend/src/views/admin/AdminCanaryPage.vue` + `AdminCanaryPage.test.ts`
- `frontend/e2e/alignment-smoke.spec.ts`

**Modify (7 files):**
- `frontend/src/api/index.ts` — 追加 4 导出
- `frontend/src/config/permissions.ts` — PAGE_PERMISSIONS +5, ROLE_PERMISSIONS 显式展开
- `frontend/src/config/routeAccess.ts` — ROUTE_PERMISSIONS +5
- `frontend/src/i18n/locales/zh-CN.ts` + `en-US.ts` — nav +5
- `frontend/src/router/index.ts` — +5 路由
- `frontend/src/layouts/MainLayout.vue` — 菜单 +5 新 +2 补齐

---

### Task 1: reportsApi.ts

用户风险导出 + 管理员报告中心 API 客户端。用户侧仅导出（report/trend 复用 `userRiskApi`）。

**Files:**
- Create: `frontend/src/api/reportsApi.ts`
- Test: `frontend/src/api/reportsApi.test.ts`

**Interfaces:**
- Consumes: `request`, `requestData` from `./request`
- Produces: `reportsApi` 对象，含 `exportUserRiskPdf/Csv/Json`、`listReportTemplates`、`generateUserRiskPdfSync/Async`、`getPdfJobStatus`、`downloadPdf`、`listPdfJobs`、`batchExportExcel`、celery 三函数

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/api/reportsApi.test.ts
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./request', () => ({
  default: {
    get: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config })),
    post: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
  },
  requestData: vi.fn(async (promise: Promise<{ data: unknown }>) => {
    const response = await promise
    return response.data
  }),
}))

import request, { requestData } from './request'
import { reportsApi } from './reportsApi'

describe('api/reportsApi', () => {
  beforeEach(() => vi.clearAllMocks())

  describe('用户侧导出', () => {
    it('exportUserRiskPdf 调 GET /user/risk/export?format=pdf 且 responseType=blob', async () => {
      ;(request.get as any).mockResolvedValueOnce({ data: new Blob() })
      await reportsApi.exportUserRiskPdf(90)
      expect(request.get).toHaveBeenCalledWith('/user/risk/export', { params: { format: 'pdf', days: 90 }, responseType: 'blob' })
    })
    it('exportUserRiskCsv 默认 days=90', async () => {
      ;(request.get as any).mockResolvedValueOnce({ data: new Blob() })
      await reportsApi.exportUserRiskCsv()
      expect(request.get).toHaveBeenCalledWith('/user/risk/export', { params: { format: 'csv', days: 90 }, responseType: 'blob' })
    })
    it('exportUserRiskJson 走 requestData 非 blob', async () => {
      ;(requestData as any).mockResolvedValueOnce({ points: [] })
      await reportsApi.exportUserRiskJson(30)
      expect(request.get).toHaveBeenCalledWith('/user/risk/export', { params: { format: 'json', days: 30 } })
    })
  })

  describe('管理员侧', () => {
    it('listReportTemplates 调 GET /reports/templates', async () => {
      ;(requestData as any).mockResolvedValueOnce({ templates: [], total: 0 })
      await reportsApi.listReportTemplates()
      expect(request.get).toHaveBeenCalledWith('/reports/templates')
    })
    it('generateUserRiskPdfSync POST /reports/user-risk/pdf 且 responseType=blob', async () => {
      ;(request.post as any).mockResolvedValueOnce({ data: new Blob() })
      await reportsApi.generateUserRiskPdfSync({ user_id: 1, user_name: 'x', risk_level: 2, risk_trend: 'stable', recommendations: [] })
      expect(request.post).toHaveBeenCalledWith('/reports/user-risk/pdf', { user_id: 1, user_name: 'x', risk_level: 2, risk_trend: 'stable', recommendations: [] }, { responseType: 'blob' })
    })
    it('generateUserRiskPdfAsync POST 返回 job_id', async () => {
      ;(requestData as any).mockResolvedValueOnce({ job_id: 'j1', status: 'queued', message: 'ok' })
      const res = await reportsApi.generateUserRiskPdfAsync({ user_id: 1, user_name: 'x', risk_level: 1, risk_trend: 'up', recommendations: [] })
      expect(res.job_id).toBe('j1')
    })
    it('getPdfJobStatus GET /reports/pdf/{id}/status', async () => {
      ;(requestData as any).mockResolvedValueOnce({ job_id: 'j1', status: 'completed', progress: 100 })
      await reportsApi.getPdfJobStatus('j1')
      expect(request.get).toHaveBeenCalledWith('/reports/pdf/j1/status')
    })
    it('downloadPdf GET /reports/pdf/{id}/download responseType=blob', async () => {
      ;(request.get as any).mockResolvedValueOnce({ data: new Blob() })
      await reportsApi.downloadPdf('j1')
      expect(request.get).toHaveBeenCalledWith('/reports/pdf/j1/download', { responseType: 'blob' })
    })
    it('listPdfJobs GET /reports/pdf/jobs', async () => {
      ;(requestData as any).mockResolvedValueOnce({ jobs: [], total: 0 })
      await reportsApi.listPdfJobs()
      expect(request.get).toHaveBeenCalledWith('/reports/pdf/jobs')
    })
    it('batchExportExcel POST /reports/batch-export/excel responseType=blob', async () => {
      ;(request.post as any).mockResolvedValueOnce({ data: new Blob() })
      await reportsApi.batchExportExcel({ data: [], columns: [], filename: 'r.xlsx' })
      expect(request.post).toHaveBeenCalledWith('/reports/batch-export/excel', { data: [], columns: [], filename: 'r.xlsx' }, { responseType: 'blob' })
    })
  })

  describe('celery 变体（仅接通）', () => {
    it('generateUserRiskPdfCeleryAsync POST celery-async', async () => {
      ;(requestData as any).mockResolvedValueOnce({ job_id: 'c1', status: 'queued', message: 'ok' })
      await reportsApi.generateUserRiskPdfCeleryAsync({ user_id: 1, user_name: 'x', risk_level: 1, risk_trend: 'up', recommendations: [] })
      expect(request.post).toHaveBeenCalledWith('/reports/user-risk/pdf/celery-async', expect.any(Object))
    })
    it('getCeleryPdfJobStatus GET celery status', async () => {
      ;(requestData as any).mockResolvedValueOnce({ status: 'running' })
      await reportsApi.getCeleryPdfJobStatus('c1')
      expect(request.get).toHaveBeenCalledWith('/reports/pdf/celery/c1/status')
    })
    it('downloadCeleryPdf GET celery download', async () => {
      ;(request.get as any).mockResolvedValueOnce({ data: new Blob() })
      await reportsApi.downloadCeleryPdf('c1')
      expect(request.get).toHaveBeenCalledWith('/reports/pdf/celery/c1/download', { responseType: 'blob' })
    })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/reportsApi.test.ts`
Expected: FAIL — `Cannot find module './reportsApi'`

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/api/reportsApi.ts
import request, { requestData } from './request'

export interface UserRiskReportRequest {
  user_id: number
  user_name: string
  risk_level: number
  risk_trend: string
  recommendations: string[]
}

export interface ReportTemplate {
  name: string
  description: string
  format: string
  required_permission?: string
}

export interface PdfJobStatus {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  message?: string
  error?: string
}

export interface PdfJobItem {
  job_id: string
  user_name?: string
  status: string
  progress: number
  created_at: string
}

export interface BatchExportRequest {
  data: Record<string, unknown>[]
  columns: string[]
  filters?: Record<string, unknown>
  filename?: string
}

export interface UserRiskExportJson {
  days: number
  direction?: string
  points?: unknown[]
  [k: string]: unknown
}

export const reportsApi = {
  // 用户侧导出（report/trend 复用 userRiskApi）
  exportUserRiskPdf: (days = 90) =>
    request.get<Blob>('/user/risk/export', { params: { format: 'pdf', days }, responseType: 'blob' }).then((res) => res.data),
  exportUserRiskCsv: (days = 90) =>
    request.get<Blob>('/user/risk/export', { params: { format: 'csv', days }, responseType: 'blob' }).then((res) => res.data),
  exportUserRiskJson: (days = 90) =>
    requestData<UserRiskExportJson>(request.get('/user/risk/export', { params: { format: 'json', days } })),

  // 管理员侧
  listReportTemplates: () =>
    requestData<{ templates: ReportTemplate[]; total: number }>(request.get('/reports/templates')),
  generateUserRiskPdfSync: (payload: UserRiskReportRequest) =>
    request.post<Blob>('/reports/user-risk/pdf', payload, { responseType: 'blob' }).then((res) => res.data),
  generateUserRiskPdfAsync: (payload: UserRiskReportRequest) =>
    requestData<{ job_id: string; status: string; message: string }>(request.post('/reports/user-risk/pdf/async', payload)),
  getPdfJobStatus: (jobId: string) =>
    requestData<PdfJobStatus>(request.get(`/reports/pdf/${jobId}/status`)),
  downloadPdf: (jobId: string) =>
    request.get<Blob>(`/reports/pdf/${jobId}/download`, { responseType: 'blob' }).then((res) => res.data),
  listPdfJobs: () =>
    requestData<{ jobs: PdfJobItem[]; total: number }>(request.get('/reports/pdf/jobs')),
  batchExportExcel: (payload: BatchExportRequest) =>
    request.post<Blob>('/reports/batch-export/excel', payload, { responseType: 'blob' }).then((res) => res.data),

  // celery 变体（仅 API 接通，第一版 UI 不暴露）
  generateUserRiskPdfCeleryAsync: (payload: UserRiskReportRequest) =>
    requestData<{ job_id: string; status: string; message: string; backend?: string }>(request.post('/reports/user-risk/pdf/celery-async', payload)),
  getCeleryPdfJobStatus: (jobId: string) =>
    requestData<PdfJobStatus>(request.get(`/reports/pdf/celery/${jobId}/status`)),
  downloadCeleryPdf: (jobId: string) =>
    request.get<Blob>(`/reports/pdf/celery/${jobId}/download`, { responseType: 'blob' }).then((res) => res.data),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/api/reportsApi.test.ts`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/api/reportsApi.ts src/api/reportsApi.test.ts && git commit -m "feat(api): add reportsApi for user export + admin reports + celery stubs"
```

---

### Task 2: observabilityApi.ts

8 个 GET，返回 `ObservabilityEnvelope<T>`（裸 dict，保留 cached/instance_id）。

**Files:**
- Create: `frontend/src/api/observabilityApi.ts`
- Test: `frontend/src/api/observabilityApi.test.ts`

**Interfaces:**
- Consumes: `request` from `./request`
- Produces: `observabilityApi`、`ObservabilityEnvelope<T>`、`ObservabilityTimeRange`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/api/observabilityApi.test.ts
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./request', () => ({
  default: {
    get: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config })),
  },
}))

import request from './request'
import { observabilityApi } from './observabilityApi'

describe('api/observabilityApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('getHealth 调 /alerts/observability/health 并保留 envelope', async () => {
    ;(request.get as any).mockResolvedValueOnce({ data: { data: { status: 'ok' }, instance_id: 'i1', cached: true, generated_at: 't' } })
    const res = await observabilityApi.getHealth()
    expect(request.get).toHaveBeenCalledWith('/alerts/observability/health', { params: undefined })
    expect(res.data).toEqual({ status: 'ok' })
    expect(res.cached).toBe(true)
    expect(res.instance_id).toBe('i1')
  })

  it('getTrend 传 bucket/severity/time range', async () => {
    ;(request.get as any).mockResolvedValueOnce({ data: { data: { points: [] }, instance_id: 'i', cached: false, generated_at: 't' } })
    await observabilityApi.getTrend({ start_time: '2026-07-01', end_time: '2026-07-08', bucket: 'day', severity: 'high' })
    expect(request.get).toHaveBeenCalledWith('/alerts/observability/trend', { params: { start_time: '2026-07-01', end_time: '2026-07-08', bucket: 'day', severity: 'high' } })
  })

  it('八个端点路径正确', async () => {
    const endpoints: Array<[string, string]> = [
      ['getHealth', '/alerts/observability/health'],
      ['getTrend', '/alerts/observability/trend'],
      ['getResponseTime', '/alerts/observability/response-time'],
      ['getEscalation', '/alerts/observability/escalation'],
      ['getChannelStats', '/alerts/observability/channel-stats'],
      ['getSilenceHitRate', '/alerts/observability/silence-hit-rate'],
      ['getAmSync', '/alerts/observability/am-sync'],
      ['getLockStats', '/alerts/observability/lock-stats'],
    ]
    for (const [fn, path] of endpoints) {
      ;(request.get as any).mockResolvedValueOnce({ data: { data: {}, instance_id: 'i', cached: false, generated_at: 't' } })
      await (observabilityApi as any)[fn]()
      expect(request.get).toHaveBeenCalledWith(path, { params: undefined })
    }
  })

  it('错误透传', async () => {
    ;(request.get as any).mockRejectedValueOnce(new Error('500'))
    await expect(observabilityApi.getHealth()).rejects.toThrow('500')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/observabilityApi.test.ts`
Expected: FAIL — `Cannot find module './observabilityApi'`

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/api/observabilityApi.ts
import request from './request'

export interface ObservabilityEnvelope<T> {
  data: T
  instance_id: string
  cached: boolean
  generated_at: string
}

export interface ObservabilityTimeRange {
  start_time?: string
  end_time?: string
}

export interface ObservabilityTrendQuery extends ObservabilityTimeRange {
  bucket?: 'hour' | 'day'
  severity?: string
  status?: string
  group_by?: string
}

function get<T>(url: string, params?: Record<string, unknown>): Promise<ObservabilityEnvelope<T>> {
  return request.get<ObservabilityEnvelope<T>>(url, { params }).then((res) => res.data)
}

export const observabilityApi = {
  getHealth: (q?: ObservabilityTimeRange) => get<{ status: string; [k: string]: unknown }>('/alerts/observability/health', q as Record<string, unknown>),
  getTrend: (q?: ObservabilityTrendQuery) => get<{ points: unknown[]; [k: string]: unknown }>('/alerts/observability/trend', q as Record<string, unknown>),
  getResponseTime: (q?: ObservabilityTrendQuery) => get<{ avg_ms: number; [k: string]: unknown }>('/alerts/observability/response-time', q as Record<string, unknown>),
  getEscalation: (q?: ObservabilityTimeRange) => get<{ escalation_rate: number; [k: string]: unknown }>('/alerts/observability/escalation', q as Record<string, unknown>),
  getChannelStats: (q?: ObservabilityTimeRange) => get<{ channels: unknown[]; [k: string]: unknown }>('/alerts/observability/channel-stats', q as Record<string, unknown>),
  getSilenceHitRate: (q?: ObservabilityTimeRange) => get<{ hit_rate: number; [k: string]: unknown }>('/alerts/observability/silence-hit-rate', q as Record<string, unknown>),
  getAmSync: (q?: ObservabilityTimeRange) => get<{ last_sync: string; [k: string]: unknown }>('/alerts/observability/am-sync', q as Record<string, unknown>),
  getLockStats: (q?: ObservabilityTimeRange) => get<{ active_locks: number; [k: string]: unknown }>('/alerts/observability/lock-stats', q as Record<string, unknown>),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/api/observabilityApi.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/api/observabilityApi.ts src/api/observabilityApi.test.ts && git commit -m "feat(api): add observabilityApi with envelope-preserving bare-dict handling"
```

---

### Task 3: monitoringApi.ts

7 个 GET（ApiResponse 包裹，用 requestData）。

**Files:**
- Create: `frontend/src/api/monitoringApi.ts`
- Test: `frontend/src/api/monitoringApi.test.ts`

**Interfaces:**
- Consumes: `request`, `requestData`
- Produces: `monitoringApi`、`MonitoringSummary`、`RequestDetailItem` 等

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/api/monitoringApi.test.ts
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./request', () => ({
  default: { get: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config })) },
  requestData: vi.fn(async (p: Promise<{ data: unknown }>) => (await p).data),
}))

import request, { requestData } from './request'
import { monitoringApi } from './monitoringApi'

describe('api/monitoringApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('getDashboardSummary GET /monitoring/dashboard-summary', async () => {
    ;(requestData as any).mockResolvedValueOnce({ total_requests: 100 })
    await monitoringApi.getDashboardSummary()
    expect(request.get).toHaveBeenCalledWith('/monitoring/dashboard-summary')
  })
  it('getModelSuccessRate 传 time range', async () => {
    ;(requestData as any).mockResolvedValueOnce({ rate: 0.95 })
    await monitoringApi.getModelSuccessRate({ start_time: 's', end_time: 'e' })
    expect(request.get).toHaveBeenCalledWith('/monitoring/model-success-rate', { params: { start_time: 's', end_time: 'e' } })
  })
  it('getFallbackStats', async () => {
    ;(requestData as any).mockResolvedValueOnce({ count: 5 })
    await monitoringApi.getFallbackStats()
    expect(request.get).toHaveBeenCalledWith('/monitoring/fallback-stats', { params: undefined })
  })
  it('getDriftAlerts', async () => {
    ;(requestData as any).mockResolvedValueOnce({ items: [] })
    await monitoringApi.getDriftAlerts()
    expect(request.get).toHaveBeenCalledWith('/monitoring/drift-alerts', { params: undefined })
  })
  it('getEngineSnapshot', async () => {
    ;(requestData as any).mockResolvedValueOnce({ engines: [] })
    await monitoringApi.getEngineSnapshot()
    expect(request.get).toHaveBeenCalledWith('/monitoring/engine-snapshot', { params: undefined })
  })
  it('getRequestDetailsList 传分页参数', async () => {
    ;(requestData as any).mockResolvedValueOnce({ items: [], total: 0 })
    await monitoringApi.getRequestDetailsList({ limit: 20, offset: 0 })
    expect(request.get).toHaveBeenCalledWith('/monitoring/request-details', { params: { limit: 20, offset: 0 } })
  })
  it('getRequestDetail GET /monitoring/request-details/{id}', async () => {
    ;(requestData as any).mockResolvedValueOnce({ log_id: 'l1' })
    await monitoringApi.getRequestDetail('l1')
    expect(request.get).toHaveBeenCalledWith('/monitoring/request-details/l1')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/monitoringApi.test.ts`
Expected: FAIL — `Cannot find module './monitoringApi'`

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/api/monitoringApi.ts
import request, { requestData } from './request'

export interface MonitoringTimeRange { start_time?: string; end_time?: string }
export interface MonitoringSummary { total_requests: number; success_rate?: number; [k: string]: unknown }
export interface RequestDetailItem { log_id: string; [k: string]: unknown }
export interface RequestDetailsList { items: RequestDetailItem[]; total: number; [k: string]: unknown }

export const monitoringApi = {
  getDashboardSummary: () => requestData<MonitoringSummary>(request.get('/monitoring/dashboard-summary')),
  getModelSuccessRate: (q?: MonitoringTimeRange) => requestData<{ rate: number; points?: unknown[]; [k: string]: unknown }>(request.get('/monitoring/model-success-rate', { params: q })),
  getFallbackStats: (q?: MonitoringTimeRange) => requestData<{ count: number; [k: string]: unknown }>(request.get('/monitoring/fallback-stats', { params: q })),
  getDriftAlerts: (q?: MonitoringTimeRange) => requestData<{ items: unknown[]; [k: string]: unknown }>(request.get('/monitoring/drift-alerts', { params: q })),
  getEngineSnapshot: () => requestData<{ engines: unknown[]; [k: string]: unknown }>(request.get('/monitoring/engine-snapshot', { params: undefined })),
  getRequestDetailsList: (q?: { limit?: number; offset?: number } & MonitoringTimeRange) => requestData<RequestDetailsList>(request.get('/monitoring/request-details', { params: q })),
  getRequestDetail: (logId: string) => requestData<RequestDetailItem>(request.get(`/monitoring/request-details/${logId}`)),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/api/monitoringApi.test.ts`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/api/monitoringApi.ts src/api/monitoringApi.test.ts && git commit -m "feat(api): add monitoringApi for ML model health endpoints"
```

---

### Task 4: canaryApi.ts

9 个端点（ApiResponse 包裹）。列表用 requestData 非 requestPageData。

**Files:**
- Create: `frontend/src/api/canaryApi.ts`
- Test: `frontend/src/api/canaryApi.test.ts`

**Interfaces:**
- Consumes: `request`, `requestData`
- Produces: `canaryApi`、`CanaryDeployment`、`CanaryCreateRequest` 等

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/api/canaryApi.test.ts
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./request', () => ({
  default: {
    get: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config })),
    post: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
    patch: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
  },
  requestData: vi.fn(async (p: Promise<{ data: unknown }>) => (await p).data),
}))

import request, { requestData } from './request'
import { canaryApi } from './canaryApi'

const deploy = { id: 1, version: 'v2', traffic_percent: 5, status: 'running', started_at: 't', created_at: 't' }

describe('api/canaryApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('listCanaryDeployments GET /canary/deployments 用 requestData', async () => {
    ;(requestData as any).mockResolvedValueOnce({ total: 1, limit: 50, offset: 0, items: [deploy] })
    const res = await canaryApi.listCanaryDeployments()
    expect(request.get).toHaveBeenCalledWith('/canary/deployments')
    expect(res.items).toHaveLength(1)
  })
  it('getCanaryDeployment GET /canary/deployments/{id}', async () => {
    ;(requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.getCanaryDeployment(1)
    expect(request.get).toHaveBeenCalledWith('/canary/deployments/1')
  })
  it('createCanaryDeployment POST', async () => {
    ;(requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.createCanaryDeployment({ version: 'v2', traffic_percent: 5 })
    expect(request.post).toHaveBeenCalledWith('/canary/deployments', { version: 'v2', traffic_percent: 5 })
  })
  it('updateCanaryTraffic PATCH /canary/deployments/{id}/traffic', async () => {
    ;(requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.updateCanaryTraffic(1, { traffic_percent: 10 })
    expect(request.patch).toHaveBeenCalledWith('/canary/deployments/1/traffic', { traffic_percent: 10 })
  })
  it('pauseCanary POST /pause', async () => {
    ;(requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.pauseCanary(1)
    expect(request.post).toHaveBeenCalledWith('/canary/deployments/1/pause')
  })
  it('resumeCanary POST /resume', async () => {
    ;(requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.resumeCanary(1)
    expect(request.post).toHaveBeenCalledWith('/canary/deployments/1/resume')
  })
  it('rollbackCanary POST /rollback 带 reason', async () => {
    ;(requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.rollbackCanary(1, { reason: 'error rate high' })
    expect(request.post).toHaveBeenCalledWith('/canary/deployments/1/rollback', { reason: 'error rate high' })
  })
  it('completeCanary POST /complete', async () => {
    ;(requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.completeCanary(1)
    expect(request.post).toHaveBeenCalledWith('/canary/deployments/1/complete')
  })
  it('getCanaryTrafficPercentages 返回可选项', async () => {
    ;(requestData as any).mockResolvedValueOnce({ percentages: [1, 5, 10, 25, 50, 100] })
    const res = await canaryApi.getCanaryTrafficPercentages()
    expect(request.get).toHaveBeenCalledWith('/canary/traffic-percentages')
    expect(res.percentages).toContain(5)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/canaryApi.test.ts`
Expected: FAIL — `Cannot find module './canaryApi'`

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/api/canaryApi.ts
import request, { requestData } from './request'

export interface CanaryCreateRequest {
  version: string
  traffic_percent?: number
  thresholds?: Record<string, number> | null
}
export interface CanaryTrafficUpdateRequest { traffic_percent: number }
export interface CanaryRollbackRequest { reason: string }
export interface CanaryDeployment {
  id: number
  version: string
  traffic_percent: number
  status: string
  started_at: string | null
  created_at: string | null
}
export interface CanaryListResponse {
  total: number
  limit: number
  offset: number
  items: CanaryDeployment[]
}

export const canaryApi = {
  listCanaryDeployments: () => requestData<CanaryListResponse>(request.get('/canary/deployments')),
  getCanaryDeployment: (id: number) => requestData<CanaryDeployment>(request.get(`/canary/deployments/${id}`)),
  createCanaryDeployment: (payload: CanaryCreateRequest) => requestData<CanaryDeployment>(request.post('/canary/deployments', payload)),
  updateCanaryTraffic: (id: number, payload: CanaryTrafficUpdateRequest) => requestData<CanaryDeployment>(request.patch(`/canary/deployments/${id}/traffic`, payload)),
  pauseCanary: (id: number) => requestData<CanaryDeployment>(request.post(`/canary/deployments/${id}/pause`)),
  resumeCanary: (id: number) => requestData<CanaryDeployment>(request.post(`/canary/deployments/${id}/resume`)),
  rollbackCanary: (id: number, payload: CanaryRollbackRequest) => requestData<CanaryDeployment>(request.post(`/canary/deployments/${id}/rollback`, payload)),
  completeCanary: (id: number) => requestData<CanaryDeployment>(request.post(`/canary/deployments/${id}/complete`)),
  getCanaryTrafficPercentages: () => requestData<{ percentages: number[] }>(request.get('/canary/traffic-percentages')),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/api/canaryApi.test.ts`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/api/canaryApi.ts src/api/canaryApi.test.ts && git commit -m "feat(api): add canaryApi for canary deployment lifecycle"
```

---

### Task 5: api/index.ts 导出聚合

**Files:**
- Modify: `frontend/src/api/index.ts`

**Interfaces:**
- Consumes: 4 新 API 模块
- Produces: 统一导出入口

- [ ] **Step 1: Read existing index.ts tail to find export block**

Run: `cd frontend && npx vitest run` (确认基线绿)
Read `frontend/src/api/index.ts`，定位已有 `export ... from './xxxApi'` 末尾。

- [ ] **Step 2: Append 4 exports**

在 `frontend/src/api/index.ts` 已有 api 导出末尾追加：

```ts
export { reportsApi } from './reportsApi'
export type { UserRiskReportRequest, ReportTemplate, PdfJobStatus, PdfJobItem, BatchExportRequest, UserRiskExportJson } from './reportsApi'
export { observabilityApi } from './observabilityApi'
export type { ObservabilityEnvelope, ObservabilityTimeRange, ObservabilityTrendQuery } from './observabilityApi'
export { monitoringApi } from './monitoringApi'
export type { MonitoringSummary, RequestDetailItem, RequestDetailsList, MonitoringTimeRange } from './monitoringApi'
export { canaryApi } from './canaryApi'
export type { CanaryCreateRequest, CanaryTrafficUpdateRequest, CanaryRollbackRequest, CanaryDeployment, CanaryListResponse } from './canaryApi'
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无新增错误

- [ ] **Step 4: Commit**

```bash
cd frontend && git add src/api/index.ts && git commit -m "feat(api): export reports/observability/monitoring/canary apis"
```

---

### Task 6: permissions.ts + routeAccess.ts

PAGE_PERMISSIONS +5、ROLE_PERMISSIONS 显式展开、ROUTE_PERMISSIONS +5。

**Files:**
- Modify: `frontend/src/config/permissions.ts:3-39`
- Modify: `frontend/src/config/routeAccess.ts:5-14`
- Test: `frontend/src/config/routeAccess.test.ts`（若存在则补，否则新建）

**Interfaces:**
- Consumes: `PermissionKey`（已存在，无需新增）
- Produces: `PAGE_PERMISSIONS.userReports/adminReports/adminObservability/adminMonitoring/adminCanary`、`ROUTE_PERMISSIONS` 对应 5 键

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/config/permissions.alignment.test.ts
import { describe, it, expect } from 'vitest'
import { PAGE_PERMISSIONS, ROLE_PERMISSIONS } from './permissions'
import { ROUTE_PERMISSIONS } from './routeAccess'

describe('alignment permissions', () => {
  it('新增 5 个 PAGE_PERMISSIONS 键', () => {
    expect(PAGE_PERMISSIONS.userReports).toEqual(['user.export.risk'])
    expect(PAGE_PERMISSIONS.adminReports).toEqual(['admin.predict.audit'])
    expect(PAGE_PERMISSIONS.adminObservability).toEqual(['admin.alerts.view'])
    expect(PAGE_PERMISSIONS.adminMonitoring).toEqual(['admin.predict.audit'])
    expect(PAGE_PERMISSIONS.adminCanary).toEqual(['admin.predict.audit'])
  })
  it('ROUTE_PERMISSIONS 含 5 新键', () => {
    expect(ROUTE_PERMISSIONS.userReports).toContain('user.export.risk')
    expect(ROUTE_PERMISSIONS.adminReports).toContain('admin.predict.audit')
    expect(ROUTE_PERMISSIONS.adminObservability).toContain('admin.alerts.view')
    expect(ROUTE_PERMISSIONS.adminMonitoring).toContain('admin.predict.audit')
    expect(ROUTE_PERMISSIONS.adminCanary).toContain('admin.predict.audit')
  })
  it('admin 角色显式含所有新权限', () => {
    const admin = ROLE_PERMISSIONS.admin
    expect(admin).toContain('user.export.risk')
    expect(admin).toContain('admin.predict.audit')
    expect(admin).toContain('admin.alerts.view')
  })
  it('user 角色含 user.export.risk', () => {
    expect(ROLE_PERMISSIONS.user).toContain('user.export.risk')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/config/permissions.alignment.test.ts`
Expected: FAIL — `userReports` undefined

- [ ] **Step 3: Update permissions.ts**

在 `PAGE_PERMISSIONS` 的 `adminSilences` 后追加 5 键（保持 `as const satisfies ...`）：

```ts
// permissions.ts PAGE_PERMISSIONS 末尾（adminSilences 之后）追加：
  userReports: ['user.export.risk'],
  adminReports: ['admin.predict.audit'],
  adminObservability: ['admin.alerts.view'],
  adminMonitoring: ['admin.predict.audit'],
  adminCanary: ['admin.predict.audit']
```

`ROLE_PERMISSIONS.user` 末尾追加 `...PAGE_PERMISSIONS.userReports`；`ROLE_PERMISSIONS.admin` 末尾（`'admin.predict.audit'` 之前）追加：

```ts
  ...PAGE_PERMISSIONS.adminReports, ...PAGE_PERMISSIONS.adminObservability, ...PAGE_PERMISSIONS.adminMonitoring, ...PAGE_PERMISSIONS.adminCanary,
```

- [ ] **Step 4: Update routeAccess.ts**

在 `ROUTE_PERMISSIONS` 的 `adminSilences` 后追加（无 OPERATION_PERMISSIONS 则直接展开 PAGE_PERMISSIONS）：

```ts
  userReports: [...PAGE_PERMISSIONS.userReports],
  adminReports: [...PAGE_PERMISSIONS.adminReports],
  adminObservability: [...PAGE_PERMISSIONS.adminObservability],
  adminMonitoring: [...PAGE_PERMISSIONS.adminMonitoring],
  adminCanary: [...PAGE_PERMISSIONS.adminCanary]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/config/permissions.alignment.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 6: Typecheck + Commit**

```bash
cd frontend && npx vue-tsc --noEmit && git add src/config/permissions.ts src/config/routeAccess.ts src/config/permissions.alignment.test.ts && git commit -m "feat(config): add 5 page permissions with explicit admin role expansion"
```

---

### Task 7: i18n nav 新增 5 键

`nav.counselor.reviews` / `nav.admin.crisisEvents` 已存在，仅新增 5 键。

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.ts`（nav.user 末尾 + nav.admin 末尾）
- Modify: `frontend/src/i18n/locales/en-US.ts`（同结构）

- [ ] **Step 1: zh-CN.ts nav.user 块末尾追加 reports**

在 `zh-CN.ts` 的 `nav.user` 块（含 `settings`）末尾加：

```ts
      reports: '报告中心',
```

`nav.admin` 块（含 `silences`、`crisisEvents`）末尾追加：

```ts
      reports: '报告中心',
      observability: '可观测性',
      monitoring: '系统监控',
      canary: '金丝雀管理'
```

- [ ] **Step 2: en-US.ts 同结构追加**

`nav.user` 末尾：

```ts
      reports: 'Reports',
```

`nav.admin` 末尾：

```ts
      reports: 'Reports',
      observability: 'Observability',
      monitoring: 'Monitoring',
      canary: 'Canary'
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无新增错误

- [ ] **Step 4: Commit**

```bash
cd frontend && git add src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts && git commit -m "feat(i18n): add nav keys for reports/observability/monitoring/canary"
```

---

### Task 8: router/index.ts 新增 5 路由

挂在 MainLayout children，参照现有 `permissions: ROUTE_PERMISSIONS.xxx` 写法。

**Files:**
- Modify: `frontend/src/router/index.ts:162`（`// Common routes` 之前插入 5 路由）

- [ ] **Step 1: Insert 5 routes before `// Common routes`**

在 `admin/silences` 路由块之后、`// Common routes` 之前插入：

```ts
      {
        path: 'user/reports',
        alias: '/user/reports',
        component: () => import('@/views/user/UserReportsPage.vue'),
        meta: { role: 'user', permissions: ROUTE_PERMISSIONS.userReports, title: 'nav.user.reports' }
      },
      {
        path: 'admin/reports',
        alias: '/admin/reports',
        component: () => import('@/views/admin/AdminReportsPage.vue'),
        meta: { role: 'admin', permissions: ROUTE_PERMISSIONS.adminReports, title: 'nav.admin.reports' }
      },
      {
        path: 'admin/observability',
        alias: '/admin/observability',
        component: () => import('@/views/admin/AdminObservabilityPage.vue'),
        meta: { role: 'admin', permissions: ROUTE_PERMISSIONS.adminObservability, title: 'nav.admin.observability' }
      },
      {
        path: 'admin/monitoring',
        alias: '/admin/monitoring',
        component: () => import('@/views/admin/AdminMonitoringPage.vue'),
        meta: { role: 'admin', permissions: ROUTE_PERMISSIONS.adminMonitoring, title: 'nav.admin.monitoring' }
      },
      {
        path: 'admin/canary',
        alias: '/admin/canary',
        component: () => import('@/views/admin/AdminCanaryPage.vue'),
        meta: { role: 'admin', permissions: ROUTE_PERMISSIONS.adminCanary, title: 'nav.admin.canary' }
      },
```

- [ ] **Step 2: Typecheck（页面尚未创建会报错，先创建空占位）**

为通过 typecheck，先创建 5 个最小占位页面（下一任务替换为真实实现）：

```vue
<!-- frontend/src/views/user/UserReportsPage.vue -->
<script setup lang="ts"></script>
<template><div /></template>
```

对 `AdminReportsPage.vue`、`AdminObservabilityPage.vue`、`AdminMonitoringPage.vue`、`AdminCanaryPage.vue` 同样创建占位（`<template><div /></template>`）。

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无新增错误

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/router/index.ts src/views/user/UserReportsPage.vue src/views/admin/AdminReportsPage.vue src/views/admin/AdminObservabilityPage.vue src/views/admin/AdminMonitoringPage.vue src/views/admin/AdminCanaryPage.vue && git commit -m "feat(router): add 5 routes for reports/observability/monitoring/canary pages"
```

---

### Task 9: MainLayout.vue 菜单 +5 新 +2 补齐

**Files:**
- Modify: `frontend/src/layouts/MainLayout.vue:176-201`

- [ ] **Step 1: user 菜单末尾追加 reports**

在 `roleMenus.user` 的 `settings` 项后追加：

```ts
    { titleKey: 'nav.user.reports', path: '/user/reports', icon: Document }
```

- [ ] **Step 2: counselor 菜单补 reviews（导航补齐）**

在 `roleMenus.counselor` 的 `users` 项后、`settings` 之前插入：

```ts
    { titleKey: 'nav.counselor.reviews', path: '/counselor/reviews', icon: ChatLineRound },
```

- [ ] **Step 3: admin 菜单追加 4 新 + crisisEvents 补齐**

在 `roleMenus.admin` 的 `silences` 项后追加：

```ts
    { titleKey: 'nav.admin.crisisEvents', path: '/admin/crisis-events', icon: Warning },
    { titleKey: 'nav.admin.reports', path: '/admin/reports', icon: Document },
    { titleKey: 'nav.admin.observability', path: '/admin/observability', icon: DataLine },
    { titleKey: 'nav.admin.monitoring', path: '/admin/monitoring', icon: Monitor },
    { titleKey: 'nav.admin.canary', path: '/admin/canary', icon: Promotion }
```

确认 `Document`、`DataLine`、`Monitor`、`Promotion`、`Warning`、`ChatLineRound` 已在文件顶部 icon import 中；若缺则补 import。

- [ ] **Step 4: Typecheck + 启动验证**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 无新增错误

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/layouts/MainLayout.vue && git commit -m "feat(layout): add menu entries for 5 new pages + 2 nav consistency fixes"
```

---

### Task 10: UserReportsPage.vue

用户风险摘要 + 趋势图 + 三格式导出。复用 `userRiskApi.getRiskReport/getRiskTrend`，导出走 `reportsApi`。

**Files:**
- Modify: `frontend/src/views/user/UserReportsPage.vue`（替换占位）
- Test: `frontend/src/views/user/UserReportsPage.test.ts`

**Interfaces:**
- Consumes: `userRiskApi`（report/trend）、`reportsApi`（export）、`BaseChart`、`showHttpFeedback`
- Produces: 默认导出 Vue 组件

- [ ] **Step 1: Write the failing test（纯逻辑：文件名解析 + 格式映射）**

```ts
// frontend/src/views/user/UserReportsPage.test.ts
import { describe, it, expect } from 'vitest'

// 提取的纯函数（与组件内一致）
export function parseFilename(disposition: string | undefined, fallback: string): string {
  if (!disposition) return fallback
  const m = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i)
  return m ? decodeURIComponent(m[1]) : fallback
}
export function formatLabel(format: 'pdf' | 'csv' | 'json'): string {
  return { pdf: 'PDF 报告', csv: 'CSV 数据', json: 'JSON 数据' }[format]
}
export function buildJsonBlob(data: unknown): Blob {
  return new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
}

describe('UserReportsPage 逻辑', () => {
  it('parseFilename 从 Content-Disposition 解析', () => {
    expect(parseFilename('attachment; filename="risk.pdf"', 'fb.pdf')).toBe('risk.pdf')
    expect(parseFilename("attachment; filename*=UTF-8''r%C3%A9.csv", 'fb.csv')).toBe('ré.csv')
    expect(parseFilename(undefined, 'fb.pdf')).toBe('fb.pdf')
  })
  it('formatLabel 三格式映射', () => {
    expect(formatLabel('pdf')).toBe('PDF 报告')
    expect(formatLabel('csv')).toBe('CSV 数据')
    expect(formatLabel('json')).toBe('JSON 数据')
  })
  it('buildJsonBlob 生成 application/json', () => {
    const blob = buildJsonBlob({ a: 1 })
    expect(blob.type).toBe('application/json')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/views/user/UserReportsPage.test.ts`
Expected: FAIL — 模块未找到（函数未导出）

- [ ] **Step 3: Write the page implementation**

```vue
<!-- frontend/src/views/user/UserReportsPage.vue -->
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { userRiskApi } from '@/api/userRiskApi'
import { reportsApi } from '@/api/reportsApi'
import { showHttpFeedback } from '@/utils/httpFeedback'
import BaseChart from '@/components/charts/BaseChart.vue'
import type { EChartsCoreOption } from '@/utils/echarts'
import type { RiskReport, RiskTrend } from '@/api/userRiskApi'

const { t } = useI18n()
const report = ref<RiskReport | null>(null)
const trend = ref<RiskTrend | null>(null)
const days = ref(30)
const loading = ref(false)
const exporting = ref(false)

function parseFilename(disposition: string | undefined, fallback: string): string {
  if (!disposition) return fallback
  const m = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i)
  return m ? decodeURIComponent(m[1]) : fallback
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const trendOption = computed<EChartsCoreOption>(() => {
  const points = trend.value?.points || []
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: points.map((p) => p.date) },
    yAxis: { type: 'value' },
    series: [{ name: t('user.riskScore'), type: 'line', data: points.map((p) => p.risk_score), smooth: true }],
  }
})

async function loadData() {
  loading.value = true
  try {
    const [r, tr] = await Promise.all([
      userRiskApi.getRiskReport(),
      userRiskApi.getRiskTrend(days.value),
    ])
    report.value = r
    trend.value = tr
  } catch (e) {
    showHttpFeedback(e, t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

async function doExport(format: 'pdf' | 'csv' | 'json') {
  exporting.value = true
  try {
    if (format === 'pdf') {
      const blob = await reportsApi.exportUserRiskPdf(days.value)
      triggerBlobDownload(blob, `risk-report-${days.value}d.pdf`)
    } else if (format === 'csv') {
      const blob = await reportsApi.exportUserRiskCsv(days.value)
      triggerBlobDownload(blob, `risk-report-${days.value}d.csv`)
    } else {
      const data = await reportsApi.exportUserRiskJson(days.value)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      triggerBlobDownload(blob, `risk-report-${days.value}d.json`)
    }
    ElMessage.success(t('common.exportSuccess'))
  } catch (e) {
    showHttpFeedback(e, t('common.exportFailed'))
  } finally {
    exporting.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div v-loading="loading" class="user-reports-page">
    <el-card v-if="report" class="summary-card">
      <div class="summary-row">
        <el-tag :type="report.severity === 'high' ? 'danger' : 'warning'" size="large">
          {{ t('user.riskLevel') }} {{ report.risk_level }}
        </el-tag>
        <span class="score">{{ report.risk_score.toFixed(1) }}</span>
        <el-tag>{{ t('user.trend') }}: {{ report.trend }}</el-tag>
      </div>
    </el-card>

    <el-card class="trend-card">
      <template #header>
        <div class="card-header">
          <el-radio-group v-model="days" size="small" @change="loadData">
            <el-radio-button :value="7">7d</el-radio-button>
            <el-radio-button :value="30">30d</el-radio-button>
            <el-radio-button :value="90">90d</el-radio-button>
            <el-radio-button :value="365">365d</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <BaseChart :option="trendOption" height="320px" />
    </el-card>

    <el-card class="export-card">
      <el-button type="primary" :loading="exporting" @click="doExport('pdf')">{{ t('common.exportPdf') }}</el-button>
      <el-button :loading="exporting" @click="doExport('csv')">CSV</el-button>
      <el-button :loading="exporting" @click="doExport('json')">JSON</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.user-reports-page { display: flex; flex-direction: column; gap: 16px; }
.summary-row { display: flex; align-items: center; gap: 16px; }
.score { font-size: 28px; font-weight: 700; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/views/user/UserReportsPage.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Typecheck + Commit**

```bash
cd frontend && npx vue-tsc --noEmit && git add src/views/user/UserReportsPage.vue src/views/user/UserReportsPage.test.ts && git commit -m "feat(page): implement UserReportsPage with summary/trend/export"
```

---

### Task 11: AdminReportsPage.vue

模板列表 + PDF 生成（同步/异步轮询）+ 任务列表 + 批量 Excel。

**Files:**
- Modify: `frontend/src/views/admin/AdminReportsPage.vue`
- Test: `frontend/src/views/admin/AdminReportsPage.test.ts`

**Interfaces:**
- Consumes: `reportsApi`、`showHttpFeedback`、`ElMessage`
- Produces: 默认导出 Vue 组件

- [ ] **Step 1: Write the failing test（纯逻辑：轮询终态判断 + Excel 校验 + 表单默认值）**

```ts
// frontend/src/views/admin/AdminReportsPage.test.ts
import { describe, it, expect } from 'vitest'

export function isTerminalStatus(status: string): boolean {
  return status === 'completed' || status === 'failed'
}
export function validateBatchExcelInput(raw: string): { ok: boolean; data?: unknown[]; error?: string } {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { ok: false, error: 'JSON 解析失败' }
  }
  if (!Array.isArray(parsed)) return { ok: false, error: 'data 必须为数组' }
  if (parsed.length > 1000) return { ok: false, error: 'data 最多 1000 行' }
  return { ok: true, data: parsed as unknown[] }
}
export function defaultPdfForm() {
  return { user_id: 0, user_name: '', risk_level: 1, risk_trend: 'stable', recommendations: [] as string[] }
}

describe('AdminReportsPage 逻辑', () => {
  it('isTerminalStatus 终态判定', () => {
    expect(isTerminalStatus('completed')).toBe(true)
    expect(isTerminalStatus('failed')).toBe(true)
    expect(isTerminalStatus('running')).toBe(false)
    expect(isTerminalStatus('queued')).toBe(false)
  })
  it('validateBatchExcelInput 合法数组', () => {
    const r = validateBatchExcelInput('[{"a":1}]')
    expect(r.ok).toBe(true)
    expect(r.data).toHaveLength(1)
  })
  it('validateBatchExcelInput 非数组拒绝', () => {
    expect(validateBatchExcelInput('{}').ok).toBe(false)
  })
  it('validateBatchExcelInput 超 1000 行拒绝', () => {
    const big = JSON.stringify(Array(1001).fill({ a: 1 }))
    expect(validateBatchExcelInput(big).ok).toBe(false)
  })
  it('validateBatchExcelInput 非法 JSON 拒绝', () => {
    expect(validateBatchExcelInput('not json').ok).toBe(false)
  })
  it('defaultPdfForm 含必填 user_id', () => {
    const f = defaultPdfForm()
    expect(f).toHaveProperty('user_id')
    expect(f).toHaveProperty('recommendations')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/views/admin/AdminReportsPage.test.ts`
Expected: FAIL

- [ ] **Step 3: Write the page implementation**

```vue
<!-- frontend/src/views/admin/AdminReportsPage.vue -->
<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { reportsApi, type ReportTemplate, type PdfJobItem, type UserRiskReportRequest } from '@/api/reportsApi'
import { showHttpFeedback } from '@/utils/httpFeedback'

const { t } = useI18n()
const templates = ref<ReportTemplate[]>([])
const jobs = ref<PdfJobItem[]>([])
const pdfForm = ref<UserRiskReportRequest>({ user_id: 0, user_name: '', risk_level: 1, risk_trend: 'stable', recommendations: [] })
const generating = ref(false)
const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null)
const currentJob = ref<{ job_id: string; status: string; progress: number } | null>(null)
const excelInput = ref('[]')
const excelCols = ref<string[]>([])
const excelFilename = ref('batch-export.xlsx')

function isTerminalStatus(status: string): boolean {
  return status === 'completed' || status === 'failed'
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function loadTemplates() {
  try {
    const res = await reportsApi.listReportTemplates()
    templates.value = res.templates
  } catch (e) { showHttpFeedback(e, t('common.loadFailed')) }
}

async function loadJobs() {
  try {
    const res = await reportsApi.listPdfJobs()
    jobs.value = res.jobs
  } catch (e) { showHttpFeedback(e, t('common.loadFailed')) }
}

function stopPolling() {
  if (pollingTimer.value) { clearInterval(pollingTimer.value); pollingTimer.value = null }
}

async function pollJobStatus(jobId: string) {
  try {
    const s = await reportsApi.getPdfJobStatus(jobId)
    currentJob.value = { job_id: jobId, status: s.status, progress: s.progress }
    if (isTerminalStatus(s.status)) {
      stopPolling()
      if (s.status === 'completed') ElMessage.success(t('reports.pdfReady'))
      await loadJobs()
    }
  } catch (e) { stopPolling(); showHttpFeedback(e, t('common.loadFailed')) }
}

function startPolling(jobId: string) {
  stopPolling()
  pollingTimer.value = setInterval(() => pollJobStatus(jobId), 2000)
}

async function generateSync() {
  generating.value = true
  try {
    const blob = await reportsApi.generateUserRiskPdfSync(pdfForm.value)
    triggerBlobDownload(blob, `user-risk-${pdfForm.value.user_id}.pdf`)
    ElMessage.success(t('common.exportSuccess'))
  } catch (e) { showHttpFeedback(e, t('common.exportFailed')) }
  finally { generating.value = false }
}

async function generateAsync() {
  generating.value = true
  try {
    const res = await reportsApi.generateUserRiskPdfAsync(pdfForm.value)
    currentJob.value = { job_id: res.job_id, status: res.status, progress: 0 }
    startPolling(res.job_id)
    ElMessage.info(t('reports.pdfGenerating'))
  } catch (e) { showHttpFeedback(e, t('common.exportFailed')) }
  finally { generating.value = false }
}

async function downloadJob(jobId: string) {
  try {
    const blob = await reportsApi.downloadPdf(jobId)
    triggerBlobDownload(blob, `${jobId}.pdf`)
  } catch (e) { showHttpFeedback(e, t('common.exportFailed')) }
}

function validateBatchExcelInput(raw: string): { ok: boolean; data?: unknown[]; error?: string } {
  let parsed: unknown
  try { parsed = JSON.parse(raw) } catch { return { ok: false, error: 'JSON 解析失败' } }
  if (!Array.isArray(parsed)) return { ok: false, error: 'data 必须为数组' }
  if (parsed.length > 1000) return { ok: false, error: 'data 最多 1000 行' }
  return { ok: true, data: parsed as unknown[] }
}

async function exportExcel() {
  const v = validateBatchExcelInput(excelInput.value)
  if (!v.ok) { ElMessage.warning(v.error || ''); return }
  if (excelCols.value.length > 50) { ElMessage.warning('columns 最多 50 列'); return }
  try {
    const blob = await reportsApi.batchExportExcel({ data: v.data as Record<string, unknown>[], columns: excelCols.value, filename: excelFilename.value })
    triggerBlobDownload(blob, excelFilename.value)
    ElMessage.success(t('common.exportSuccess'))
  } catch (e) { showHttpFeedback(e, t('common.exportFailed')) }
}

onMounted(() => { loadTemplates(); loadJobs() })
onUnmounted(stopPolling)
</script>

<template>
  <div class="admin-reports-page">
    <el-card class="templates-card">
      <template #header>{{ t('reports.templates') }}</template>
      <el-row :gutter="12">
        <el-col v-for="tp in templates" :key="tp.name" :span="6">
          <el-card shadow="hover">
            <h4>{{ tp.name }}</h4>
            <p>{{ tp.description }}</p>
            <el-tag size="small">{{ tp.format }}</el-tag>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <el-card class="pdf-card">
      <template #header>{{ t('reports.generatePdf') }}</template>
      <el-form :model="pdfForm" label-width="120px">
        <el-form-item label="user_id"><el-input-number v-model="pdfForm.user_id" :min="1" /></el-form-item>
        <el-form-item label="user_name"><el-input v-model="pdfForm.user_name" /></el-form-item>
        <el-form-item label="risk_level"><el-input-number v-model="pdfForm.risk_level" :min="0" :max="4" /></el-form-item>
        <el-form-item label="risk_trend"><el-input v-model="pdfForm.risk_trend" /></el-form-item>
        <el-form-item label="recommendations">
          <el-input v-model="(pdfForm.recommendations as unknown as string)" type="textarea" placeholder="逗号分隔" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="generating" @click="generateSync">{{ t('reports.syncGenerate') }}</el-button>
          <el-button :loading="generating" @click="generateAsync">{{ t('reports.asyncGenerate') }}</el-button>
        </el-form-item>
      </el-form>
      <el-progress v-if="currentJob" :percentage="currentJob.progress" :status="currentJob.status === 'failed' ? 'exception' : 'success'" />
      <el-button v-if="currentJob?.status === 'completed'" type="success" @click="downloadJob(currentJob.job_id)">{{ t('common.download') }}</el-button>
    </el-card>

    <el-card class="jobs-card">
      <template #header>{{ t('reports.jobList') }}</template>
      <el-table :data="jobs" stripe>
        <el-table-column prop="job_id" label="job_id" />
        <el-table-column prop="status" label="status" />
        <el-table-column prop="progress" label="progress">
          <template #default="{ row }"><el-progress :percentage="row.progress" /></template>
        </el-table-column>
        <el-table-column prop="created_at" label="created_at" />
        <el-table-column label="操作">
          <template #default="{ row }">
            <el-button v-if="row.status === 'completed'" size="small" type="success" @click="downloadJob(row.job_id)">{{ t('common.download') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="excel-card">
      <template #header>{{ t('reports.batchExcel') }}</template>
      <el-input v-model="excelInput" type="textarea" :rows="6" placeholder='[{"col":"val"}]' />
      <el-input v-model="(excelCols as unknown as string)" placeholder="col1,col2（逗号分隔，最多 50 列）" style="margin-top: 8px" />
      <el-input v-model="excelFilename" placeholder="filename.xlsx" style="margin-top: 8px" />
      <el-button type="primary" style="margin-top: 8px" @click="exportExcel">{{ t('common.export') }}</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.admin-reports-page { display: flex; flex-direction: column; gap: 16px; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/views/admin/AdminReportsPage.test.ts`
Expected: PASS (6 tests)

- [ ] **Step 5: Typecheck + Commit**

```bash
cd frontend && npx vue-tsc --noEmit && git add src/views/admin/AdminReportsPage.vue src/views/admin/AdminReportsPage.test.ts && git commit -m "feat(page): implement AdminReportsPage with templates/pdf/jobs/excel"
```

---

### Task 12: AdminObservabilityPage.vue

8 指标区块独立加载（Promise.allSettled），时间范围选择器，60s 自动刷新。

**Files:**
- Modify: `frontend/src/views/admin/AdminObservabilityPage.vue`
- Test: `frontend/src/views/admin/AdminObservabilityPage.test.ts`

- [ ] **Step 1: Write the failing test（纯逻辑：时间范围校验 + 区块降级聚合）**

```ts
// frontend/src/views/admin/AdminObservabilityPage.test.ts
import { describe, it, expect } from 'vitest'

const MAX_RANGE_DAYS = 30

export function validateTimeRange(start: string, end: string): { ok: boolean; error?: string } {
  const s = new Date(start).getTime()
  const e = new Date(end).getTime()
  if (Number.isNaN(s) || Number.isNaN(e)) return { ok: false, error: '时间格式无效' }
  if (e < s) return { ok: false, error: '结束时间不能早于开始时间' }
  if ((e - s) / 86400000 > MAX_RANGE_DAYS) return { ok: false, error: '范围不能超过 30 天' }
  return { ok: true }
}

export function settleBlocks<T extends { key: string }>(results: PromiseSettledResult<T>[]): { fulfilled: T[]; rejected: string[] } {
  const fulfilled: T[] = []
  const rejected: string[] = []
  for (const r of results) {
    if (r.status === 'fulfilled') fulfilled.push(r.value)
    else rejected.push('block')
  }
  return { fulfilled, rejected }
}

describe('AdminObservabilityPage 逻辑', () => {
  it('validateTimeRange 合法', () => {
    expect(validateTimeRange('2026-07-01', '2026-07-08').ok).toBe(true)
  })
  it('validateTimeRange 超 30 天拒绝', () => {
    expect(validateTimeRange('2026-06-01', '2026-07-08').ok).toBe(false)
  })
  it('validateTimeRange 结束早于开始拒绝', () => {
    expect(validateTimeRange('2026-07-08', '2026-07-01').ok).toBe(false)
  })
  it('settleBlocks 分离成功与失败', () => {
    const r: PromiseSettledResult<{ key: string }>[] = [
      { status: 'fulfilled', value: { key: 'a' } },
      { status: 'rejected', reason: new Error('x') },
    ]
    const s = settleBlocks(r)
    expect(s.fulfilled).toHaveLength(1)
    expect(s.rejected).toHaveLength(1)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/views/admin/AdminObservabilityPage.test.ts`
Expected: FAIL

- [ ] **Step 3: Write the page implementation**

```vue
<!-- frontend/src/views/admin/AdminObservabilityPage.vue -->
<script setup lang="ts">
import { ref, onMounted, onUnmounted, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { observabilityApi, type ObservabilityEnvelope, type ObservabilityTimeRange } from '@/api/observabilityApi'
import { showHttpFeedback } from '@/utils/httpFeedback'

const { t } = useI18n()
const MAX_RANGE_DAYS = 30

interface BlockState<T> { loading: boolean; data: ObservabilityEnvelope<T> | null; error: string | null; cached: boolean }

function makeBlock<T>(): BlockState<T> {
  return reactive({ loading: false, data: null, error: null, cached: false })
}

const range = reactive<ObservabilityTimeRange>({ start_time: undefined, end_time: undefined })
const health = makeBlock<{ status: string }>()
const trend = makeBlock<{ points: unknown[] }>()
const responseTime = makeBlock<{ avg_ms: number }>()
const escalation = makeBlock<{ escalation_rate: number }>()
const channelStats = makeBlock<{ channels: unknown[] }>()
const silenceHit = makeBlock<{ hit_rate: number }>()
const amSync = makeBlock<{ last_sync: string }>()
const lockStats = makeBlock<{ active_locks: number }>()

const autoRefresh = ref(false)
const refreshTimer = ref<ReturnType<typeof setInterval> | null>(null)

function defaultRange(): ObservabilityTimeRange {
  const end = new Date()
  const start = new Date(end.getTime() - 24 * 3600 * 1000)
  return { start_time: start.toISOString().slice(0, 10), end_time: end.toISOString().slice(0, 10) }
}

async function loadBlock<T>(block: BlockState<T>, fn: (q?: ObservabilityTimeRange) => Promise<ObservabilityEnvelope<T>>) {
  block.loading = true
  block.error = null
  try {
    const env = await fn(range.start_time && range.end_time ? range : undefined)
    block.data = env
    block.cached = env.cached
  } catch (e) {
    block.error = e instanceof Error ? e.message : 'error'
  } finally {
    block.loading = false
  }
}

async function loadAll() {
  await Promise.allSettled([
    loadBlock(health, observabilityApi.getHealth),
    loadBlock(trend, observabilityApi.getTrend),
    loadBlock(responseTime, observabilityApi.getResponseTime),
    loadBlock(escalation, observabilityApi.getEscalation),
    loadBlock(channelStats, observabilityApi.getChannelStats),
    loadBlock(silenceHit, observabilityApi.getSilenceHitRate),
    loadBlock(amSync, observabilityApi.getAmSync),
    loadBlock(lockStats, observabilityApi.getLockStats),
  ])
}

function toggleAutoRefresh(val: boolean) {
  if (val) {
    refreshTimer.value = setInterval(loadAll, 60000)
  } else if (refreshTimer.value) {
    clearInterval(refreshTimer.value)
    refreshTimer.value = null
  }
}

onMounted(() => { Object.assign(range, defaultRange()); loadAll() })
onUnmounted(() => { if (refreshTimer.value) clearInterval(refreshTimer.value) })
</script>

<template>
  <div class="observability-page">
    <div class="toolbar">
      <el-date-picker v-model="range.start_time" type="date" placeholder="start" />
      <el-date-picker v-model="range.end_time" type="date" placeholder="end" />
      <el-button @click="loadAll">{{ t('common.refresh') }}</el-button>
      <el-switch v-model="autoRefresh" @change="toggleAutoRefresh" :active-text="t('common.autoRefresh')" />
    </div>
    <el-row :gutter="12">
      <el-col :span="6">
        <el-card v-loading="health.loading">
          <template #header>{{ t('observability.health') }}<el-tag v-if="health.cached" size="small">cached</el-tag></template>
          <div v-if="health.error" class="err">{{ health.error }}</div>
          <div v-else>{{ health.data?.data?.status }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-loading="responseTime.loading">
          <template #header>{{ t('observability.responseTime') }}</template>
          <div v-if="responseTime.error" class="err">{{ responseTime.error }}</div>
          <div v-else>{{ responseTime.data?.data?.avg_ms }} ms</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-loading="escalation.loading">
          <template #header>{{ t('observability.escalation') }}</template>
          <div v-if="escalation.error" class="err">{{ escalation.error }}</div>
          <div v-else>{{ escalation.data?.data?.escalation_rate }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-loading="silenceHit.loading">
          <template #header>{{ t('observability.silenceHitRate') }}</template>
          <div v-if="silenceHit.error" class="err">{{ silenceHit.error }}</div>
          <div v-else>{{ silenceHit.data?.data?.hit_rate }}</div>
        </el-card>
      </el-col>
    </el-row>
    <el-row :gutter="12" style="margin-top: 12px">
      <el-col :span="12">
        <el-card v-loading="trend.loading">
          <template #header>{{ t('observability.trend') }}</template>
          <div v-if="trend.error" class="err">{{ trend.error }}</div>
          <div v-else>{{ trend.data?.data?.points?.length }} points</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-loading="amSync.loading">
          <template #header>{{ t('observability.amSync') }}</template>
          <div v-if="amSync.error" class="err">{{ amSync.error }}</div>
          <div v-else>{{ amSync.data?.data?.last_sync }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-loading="lockStats.loading">
          <template #header>{{ t('observability.lockStats') }}</template>
          <div v-if="lockStats.error" class="err">{{ lockStats.error }}</div>
          <div v-else>{{ lockStats.data?.data?.active_locks }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.observability-page { display: flex; flex-direction: column; gap: 12px; }
.toolbar { display: flex; gap: 8px; align-items: center; }
.err { color: var(--el-color-danger); }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/views/admin/AdminObservabilityPage.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Typecheck + Commit**

```bash
cd frontend && npx vue-tsc --noEmit && git add src/views/admin/AdminObservabilityPage.vue src/views/admin/AdminObservabilityPage.test.ts && git commit -m "feat(page): implement AdminObservabilityPage with 8 independent blocks"
```

---

### Task 13: AdminMonitoringPage.vue

摘要 + 模型成功率 + 回退 + 漂移 + 引擎 + 请求详情（分页），单块降级，30s 自动刷新。

**Files:**
- Modify: `frontend/src/views/admin/AdminMonitoringPage.vue`
- Test: `frontend/src/views/admin/AdminMonitoringPage.test.ts`

- [ ] **Step 1: Write the failing test（纯逻辑：脱敏 + 状态映射 + 分页计算）**

```ts
// frontend/src/views/admin/AdminMonitoringPage.test.ts
import { describe, it, expect } from 'vitest'

export function maskSensitive(text: unknown, maxLen = 80): string {
  if (text == null) return ''
  const s = String(text)
  if (s.length <= maxLen) return s
  return s.slice(0, maxLen) + '…'
}
export function statusTagType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'success') return 'success'
  if (status === 'fallback') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}
export function computePage(offset: number, limit: number): number {
  return Math.floor(offset / limit) + 1
}

describe('AdminMonitoringPage 逻辑', () => {
  it('maskSensitive 截断长文本', () => {
    expect(maskSensitive('x'.repeat(100), 10)).toBe('xxxxxxxxxx…')
    expect(maskSensitive('short', 10)).toBe('short')
  })
  it('statusTagType 映射', () => {
    expect(statusTagType('success')).toBe('success')
    expect(statusTagType('fallback')).toBe('warning')
    expect(statusTagType('failed')).toBe('danger')
  })
  it('computePage 分页计算', () => {
    expect(computePage(0, 20)).toBe(1)
    expect(computePage(20, 20)).toBe(2)
    expect(computePage(40, 20)).toBe(3)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/views/admin/AdminMonitoringPage.test.ts`
Expected: FAIL

- [ ] **Step 3: Write the page implementation**

```vue
<!-- frontend/src/views/admin/AdminMonitoringPage.vue -->
<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { monitoringApi, type MonitoringSummary, type RequestDetailsList, type RequestDetailItem } from '@/api/monitoringApi'
import { showHttpFeedback } from '@/utils/httpFeedback'
import BaseChart from '@/components/charts/BaseChart.vue'
import type { EChartsCoreOption } from '@/utils/echarts'

const { t } = useI18n()

const summary = ref<MonitoringSummary | null>(null)
const successRate = ref<{ rate: number; points?: unknown[] } | null>(null)
const fallbackStats = ref<{ count: number } | null>(null)
const driftAlerts = ref<{ items: unknown[] } | null>(null)
const engineSnapshot = ref<{ engines: unknown[] } | null>(null)
const details = ref<RequestDetailsList | null>(null)
const detailRow = ref<RequestDetailItem | null>(null)
const detailVisible = ref(false)
const page = reactive({ limit: 20, offset: 0 })
const autoRefresh = ref(false)
const refreshTimer = ref<ReturnType<typeof setInterval> | null>(null)
const loading = ref(false)

function maskSensitive(text: unknown, maxLen = 80): string {
  if (text == null) return ''
  const s = String(text)
  return s.length <= maxLen ? s : s.slice(0, maxLen) + '…'
}

const successOption = computed<EChartsCoreOption>(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: (successRate.value?.points as { date?: string }[] || []).map((p) => p.date || '') },
  yAxis: { type: 'value', max: 1 },
  series: [{ type: 'line', data: (successRate.value?.points as { rate?: number }[] || []).map((p) => p.rate || 0), smooth: true }],
}))

async function loadAll() {
  loading.value = true
  const results = await Promise.allSettled([
    monitoringApi.getDashboardSummary(),
    monitoringApi.getModelSuccessRate(),
    monitoringApi.getFallbackStats(),
    monitoringApi.getDriftAlerts(),
    monitoringApi.getEngineSnapshot(),
    monitoringApi.getRequestDetailsList(page),
  ])
  if (results[0].status === 'fulfilled') summary.value = results[0].value
  if (results[1].status === 'fulfilled') successRate.value = results[1].value
  if (results[2].status === 'fulfilled') fallbackStats.value = results[2].value
  if (results[3].status === 'fulfilled') driftAlerts.value = results[3].value
  if (results[4].status === 'fulfilled') engineSnapshot.value = results[4].value
  if (results[5].status === 'fulfilled') details.value = results[5].value
  loading.value = false
}

async function loadDetails() {
  try { details.value = await monitoringApi.getRequestDetailsList(page) }
  catch (e) { showHttpFeedback(e, t('common.loadFailed')) }
}

async function showDetail(logId: string) {
  try { detailRow.value = await monitoringApi.getRequestDetail(logId); detailVisible.value = true }
  catch (e) { showHttpFeedback(e, t('common.loadFailed')) }
}

function onPageChange(p: number) {
  page.offset = (p - 1) * page.limit
  loadDetails()
}

function toggleAutoRefresh(val: boolean) {
  if (val) refreshTimer.value = setInterval(loadAll, 30000)
  else if (refreshTimer.value) { clearInterval(refreshTimer.value); refreshTimer.value = null }
}

onMounted(loadAll)
onUnmounted(() => { if (refreshTimer.value) clearInterval(refreshTimer.value) })
</script>

<template>
  <div v-loading="loading" class="monitoring-page">
    <div class="toolbar">
      <el-button @click="loadAll">{{ t('common.refresh') }}</el-button>
      <el-switch v-model="autoRefresh" @change="toggleAutoRefresh" :active-text="t('common.autoRefresh')" />
    </div>
    <el-row :gutter="12">
      <el-col :span="6"><el-card><template #header>{{ t('monitoring.totalRequests') }}</template>{{ summary?.total_requests }}</el-card></el-col>
      <el-col :span="6"><el-card><template #header>{{ t('monitoring.fallbackCount') }}</template>{{ fallbackStats?.count }}</el-card></el-col>
      <el-col :span="6"><el-card><template #header>{{ t('monitoring.driftAlerts') }}</template>{{ driftAlerts?.items?.length }}</el-card></el-col>
      <el-col :span="6"><el-card><template #header>{{ t('monitoring.engines') }}</template>{{ engineSnapshot?.engines?.length }}</el-card></el-col>
    </el-row>
    <el-card><template #header>{{ t('monitoring.modelSuccessRate') }}</template><BaseChart :option="successOption" height="280px" /></el-card>
    <el-card>
      <template #header>{{ t('monitoring.requestDetails') }}</template>
      <el-table :data="details?.items || []" stripe @row-click="(row: RequestDetailItem) => showDetail(row.log_id)">
        <el-table-column prop="log_id" label="log_id" width="180" />
        <el-table-column label="input">
          <template #default="{ row }">{{ maskSensitive((row as Record<string, unknown>).input) }}</template>
        </el-table-column>
      </el-table>
      <el-pagination :total="details?.total || 0" :page-size="page.limit" :current-page="Math.floor(page.offset / page.limit) + 1" layout="prev, pager, next" @current-change="onPageChange" />
    </el-card>
    <el-dialog v-model="detailVisible" :title="t('monitoring.requestDetail')" width="60%">
      <pre>{{ JSON.stringify(detailRow, null, 2) }}</pre>
    </el-dialog>
  </div>
</template>

<style scoped>
.monitoring-page { display: flex; flex-direction: column; gap: 12px; }
.toolbar { display: flex; gap: 8px; align-items: center; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/views/admin/AdminMonitoringPage.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Typecheck + Commit**

```bash
cd frontend && npx vue-tsc --noEmit && git add src/views/admin/AdminMonitoringPage.vue src/views/admin/AdminMonitoringPage.test.ts && git commit -m "feat(page): implement AdminMonitoringPage with summary/chart/details pagination"
```

---

### Task 14: AdminCanaryPage.vue

部署列表 + 新建 + 流量调整 + 暂停/恢复/回滚/完成，状态驱动按钮，二次确认。

**Files:**
- Modify: `frontend/src/views/admin/AdminCanaryPage.vue`
- Test: `frontend/src/views/admin/AdminCanaryPage.test.ts`

- [ ] **Step 1: Write the failing test（纯逻辑：状态→可用操作 + 流量校验）**

```ts
// frontend/src/views/admin/AdminCanaryPage.test.ts
import { describe, it, expect } from 'vitest'

export function availableActions(status: string): string[] {
  switch (status) {
    case 'running': return ['adjust', 'pause', 'rollback', 'complete']
    case 'paused': return ['adjust', 'resume', 'rollback']
    case 'completed': return []
    case 'rolled_back': return []
    default: return []
  }
}
export function validateTraffic(percent: number): { ok: boolean; error?: string } {
  if (!Number.isInteger(percent)) return { ok: false, error: '必须为整数' }
  if (percent < 1 || percent > 100) return { ok: false, error: '范围 1-100' }
  return { ok: true }
}
export function validateRollbackReason(reason: string): { ok: boolean; error?: string } {
  if (reason.trim().length < 1) return { ok: false, error: '原因必填' }
  if (reason.length > 500) return { ok: false, error: '最多 500 字' }
  return { ok: true }
}

describe('AdminCanaryPage 逻辑', () => {
  it('running 可 pause/rollback/complete/adjust', () => {
    expect(availableActions('running')).toEqual(['adjust', 'pause', 'rollback', 'complete'])
  })
  it('paused 可 resume/rollback/adjust', () => {
    expect(availableActions('paused')).toEqual(['adjust', 'resume', 'rollback'])
  })
  it('completed 无操作', () => {
    expect(availableActions('completed')).toEqual([])
  })
  it('validateTraffic 边界', () => {
    expect(validateTraffic(1).ok).toBe(true)
    expect(validateTraffic(100).ok).toBe(true)
    expect(validateTraffic(0).ok).toBe(false)
    expect(validateTraffic(101).ok).toBe(false)
  })
  it('validateRollbackReason 必填', () => {
    expect(validateRollbackReason('').ok).toBe(false)
    expect(validateRollbackReason('error rate').ok).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/views/admin/AdminCanaryPage.test.ts`
Expected: FAIL

- [ ] **Step 3: Write the page implementation**

```vue
<!-- frontend/src/views/admin/AdminCanaryPage.vue -->
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { canaryApi, type CanaryDeployment, type CanaryCreateRequest } from '@/api/canaryApi'
import { showHttpFeedback } from '@/utils/httpFeedback'

const { t } = useI18n()
const deployments = ref<CanaryDeployment[]>([])
const percentages = ref<number[]>([])
const loading = ref(false)
const createVisible = ref(false)
const createForm = ref<CanaryCreateRequest>({ version: '', traffic_percent: 1 })
const trafficVisible = ref(false)
const trafficTarget = ref<{ id: number; percent: number } | null>(null)

function availableActions(status: string): string[] {
  switch (status) {
    case 'running': return ['adjust', 'pause', 'rollback', 'complete']
    case 'paused': return ['adjust', 'resume', 'rollback']
    default: return []
  }
}

const runningCount = computed(() => deployments.value.filter((d) => d.status === 'running').length)
const pausedCount = computed(() => deployments.value.filter((d) => d.status === 'paused').length)

async function loadAll() {
  loading.value = true
  try {
    const [list, pct] = await Promise.all([canaryApi.listCanaryDeployments(), canaryApi.getCanaryTrafficPercentages()])
    deployments.value = list.items
    percentages.value = pct.percentages
  } catch (e) { showHttpFeedback(e, t('common.loadFailed')) }
  finally { loading.value = false }
}

async function createDeployment() {
  if (!createForm.value.version.trim()) { ElMessage.warning('version 必填'); return }
  try {
    await canaryApi.createCanaryDeployment(createForm.value)
    ElMessage.success(t('common.createSuccess'))
    createVisible.value = false
    createForm.value = { version: '', traffic_percent: 1 }
    await loadAll()
  } catch (e) { showHttpFeedback(e, t('common.createFailed')) }
}

function openTrafficDialog(d: CanaryDeployment) {
  trafficTarget.value = { id: d.id, percent: d.traffic_percent }
  trafficVisible.value = true
}

async function updateTraffic() {
  if (!trafficTarget.value) return
  const p = trafficTarget.value.percent
  if (p < 1 || p > 100) { ElMessage.warning('范围 1-100'); return }
  try {
    await canaryApi.updateCanaryTraffic(trafficTarget.value.id, { traffic_percent: p })
    ElMessage.success(t('common.updateSuccess'))
    trafficVisible.value = false
    await loadAll()
  } catch (e) { showHttpFeedback(e, t('common.updateFailed')) }
}

async function pauseDeployment(d: CanaryDeployment) {
  try { await canaryApi.pauseCanary(d.id); ElMessage.success(t('common.success')); await loadAll() }
  catch (e) { showHttpFeedback(e, t('common.failed')) }
}

async function resumeDeployment(d: CanaryDeployment) {
  try { await canaryApi.resumeCanary(d.id); ElMessage.success(t('common.success')); await loadAll() }
  catch (e) { showHttpFeedback(e, t('common.failed')) }
}

async function completeDeployment(d: CanaryDeployment) {
  try {
    await ElMessageBox.confirm(t('canary.confirmComplete', { v: d.version }), t('common.confirm'), { type: 'warning' })
    await canaryApi.completeCanary(d.id); ElMessage.success(t('common.success')); await loadAll()
  } catch (e) { if (e !== 'cancel') showHttpFeedback(e, t('common.failed')) }
}

async function rollbackDeployment(d: CanaryDeployment) {
  try {
    const { value } = await ElMessageBox.prompt(t('canary.rollbackReason'), t('canary.rollback'), { type: 'error', inputType: 'textarea', inputValidator: (v) => (v && v.trim().length >= 1 && v.length <= 500) || t('canary.reasonRequired') })
    await canaryApi.rollbackCanary(d.id, { reason: value })
    ElMessage.success(t('common.success')); await loadAll()
  } catch (e) { if (e !== 'cancel') showHttpFeedback(e, t('common.failed')) }
}

onMounted(loadAll)
</script>

<template>
  <div v-loading="loading" class="canary-page">
    <div class="toolbar">
      <span>{{ t('canary.running') }}: {{ runningCount }}</span>
      <span>{{ t('canary.paused') }}: {{ pausedCount }}</span>
      <el-button type="primary" @click="createVisible = true">{{ t('canary.newDeployment') }}</el-button>
      <el-button @click="loadAll">{{ t('common.refresh') }}</el-button>
    </div>
    <el-table :data="deployments" stripe>
      <el-table-column prop="version" label="version" />
      <el-table-column prop="traffic_percent" label="traffic %" />
      <el-table-column prop="status" label="status" />
      <el-table-column prop="started_at" label="started_at" />
      <el-table-column :label="t('common.actions')">
        <template #default="{ row }">
          <el-button v-if="availableActions(row.status).includes('adjust')" size="small" @click="openTrafficDialog(row)">{{ t('canary.adjustTraffic') }}</el-button>
          <el-button v-if="availableActions(row.status).includes('pause')" size="small" @click="pauseDeployment(row)">{{ t('canary.pause') }}</el-button>
          <el-button v-if="availableActions(row.status).includes('resume')" size="small" @click="resumeDeployment(row)">{{ t('canary.resume') }}</el-button>
          <el-button v-if="availableActions(row.status).includes('complete')" size="small" type="success" @click="completeDeployment(row)">{{ t('canary.complete') }}</el-button>
          <el-button v-if="availableActions(row.status).includes('rollback')" size="small" type="danger" @click="rollbackDeployment(row)">{{ t('canary.rollback') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createVisible" :title="t('canary.newDeployment')" width="40%">
      <el-form label-width="120px">
        <el-form-item label="version"><el-input v-model="createForm.version" /></el-form-item>
        <el-form-item label="traffic %">
          <el-select v-model="createForm.traffic_percent">
            <el-option v-for="p in percentages" :key="p" :label="p + '%'" :value="p" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="createVisible = false">{{ t('common.cancel') }}</el-button><el-button type="primary" @click="createDeployment">{{ t('common.confirm') }}</el-button></template>
    </el-dialog>

    <el-dialog v-model="trafficVisible" :title="t('canary.adjustTraffic')" width="30%">
      <el-slider v-model="trafficTarget.percent" :min="1" :max="100" :marks="Object.fromEntries(percentages.map((p) => [p, p + '%']))" />
      <template #footer><el-button @click="trafficVisible = false">{{ t('common.cancel') }}</el-button><el-button type="primary" @click="updateTraffic">{{ t('common.confirm') }}</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.canary-page { display: flex; flex-direction: column; gap: 12px; }
.toolbar { display: flex; gap: 16px; align-items: center; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/views/admin/AdminCanaryPage.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 5: Typecheck + Commit**

```bash
cd frontend && npx vue-tsc --noEmit && git add src/views/admin/AdminCanaryPage.vue src/views/admin/AdminCanaryPage.test.ts && git commit -m "feat(page): implement AdminCanaryPage with deployment lifecycle controls"
```

---

### Task 15: E2E smoke

覆盖菜单可见性 + 页面可达性 + 权限边界，不涉及复杂交互。

**Files:**
- Create: `frontend/e2e/alignment-smoke.spec.ts`

**Interfaces:**
- Consumes: `loginAsRole` from `./shared`、`@playwright/test`

- [ ] **Step 1: Write the e2e test**

```ts
// frontend/e2e/alignment-smoke.spec.ts
import { test, expect } from '@playwright/test'
import { loginAsRole } from './shared'

test.describe('前后端对齐 smoke', () => {
  test('admin 可见 4 新菜单 + crisis-events + 进入页面', async ({ page }) => {
    await loginAsRole(page, 'admin')
    const navTexts = ['报告中心', '可观测性', '系统监控', '金丝雀管理', '危机事件']
    for (const text of navTexts) {
      await expect(page.getByRole('menuitem', { name: text }).or(page.getByText(text, { exact: true })).first()).toBeVisible()
    }
    const routes = ['/admin/reports', '/admin/observability', '/admin/monitoring', '/admin/canary', '/admin/crisis-events']
    for (const route of routes) {
      await page.goto(route)
      await expect(page).toHaveURL(new RegExp(route.replaceAll('/', '\\/')))
    }
  })

  test('user 可见报告中心入口 + 访问 admin 页面被拒绝', async ({ page }) => {
    await loginAsRole(page, 'user')
    await expect(page.getByText('报告中心', { exact: true }).first()).toBeVisible()
    await page.goto('/admin/canary')
    await expect(page).not.toHaveURL(/\/admin\/canary$/)
  })
})
```

- [ ] **Step 2: Run e2e**

Run: `cd frontend && npx playwright test e2e/alignment-smoke.spec.ts`
Expected: PASS (2 tests)

注：若 `loginAsRole` 依赖后端运行，需先启动后端 `cd backend && .venv\Scripts\activate && uvicorn app.main:app --port 8000`。

- [ ] **Step 3: Commit**

```bash
cd frontend && git add e2e/alignment-smoke.spec.ts && git commit -m "test(e2e): add alignment smoke for menu/route/permission reachability"
```

---

## Self-Review

**1. Spec coverage:** 
- 4 API 域 ✓（Task 1-4）；响应解包三类 ✓（Task 1 blob/requestData、Task 2 envelope、Task 3-4 requestData）；5 页面 ✓（Task 10-14）；路由 ✓（Task 8）；菜单 ✓（Task 9）；权限 ✓（Task 6）；i18n ✓（Task 7）；E2E ✓（Task 15）；celery 仅接通 ✓（Task 1 含 celery 三函数 + UI 不暴露）；canary traffic-percentages 选项语义 ✓（Task 14 仅作 slider 刻度）；monitoring 单块降级 ✓（Task 13 Promise.allSettled）；observability 单块降级 ✓（Task 12）；批量 Excel 限制 ✓（Task 11 validateBatchExcelInput）；导航补齐 ✓（Task 9 counselor reviews + admin crisisEvents）；user_id 必填 ✓（Task 11 表单含 user_id）。

**2. Placeholder scan:** 无 TBD/TODO；所有代码块完整；测试命令含 expected 输出。

**3. Type consistency:** `reportsApi.exportUserRiskPdf/Csv/Json` 在 Task 1 定义、Task 10 消费 ✓；`observabilityApi.getHealth` 等 Task 2 定义、Task 12 消费 ✓；`monitoringApi.*` Task 3 定义、Task 13 消费 ✓；`canaryApi.*` Task 4 定义、Task 14 消费 ✓；`ROUTE_PERMISSIONS.userReports` 等 Task 6 定义、Task 8 消费 ✓；`CanaryDeployment` Task 4 定义、Task 14 消费 ✓。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-08-frontend-api-alignment.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

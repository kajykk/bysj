// frontend/src/api/reportsApi.ts
import request, { requestData } from './request'

export interface RiskTrendItem {
  date: string
  score: number
  level: string
}

export interface UserRiskReportRequest {
  user_id: number
  user_name: string
  risk_level: string
  risk_trend: RiskTrendItem[]
  recommendations: string[]
}

export interface ReportTemplate {
  // M-FIX-003: 与后端 REPORT_TEMPLATES (reports.py:42-71) 对齐:
  // id/name/description/formats[]/permissions[]，无 format/required_permission
  id: string
  name: string
  description: string
  formats: string[]
  permissions: string[]
}

export interface PdfJobStatus {
  // M-FIX-003: 兼容进程内 PdfJobStore (id) 与 celery 变体 (job_id) 两种键
  id?: string
  job_id?: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  message?: string
  error?: string
}

export interface PdfJobItem {
  id: string
  job_id?: string
  user_name?: string
  status: string
  progress: number
  created_at: string
  error?: string | null
}

export interface BatchExportDataItem {
  data: Record<string, unknown>
}

export interface BatchExportRequest {
  data: BatchExportDataItem[]
  columns?: string[]
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

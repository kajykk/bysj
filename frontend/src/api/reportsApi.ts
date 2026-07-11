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
  id: string
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

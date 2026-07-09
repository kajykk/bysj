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
      (request.get as any).mockResolvedValueOnce({ data: new Blob() })
      await reportsApi.exportUserRiskPdf(90)
      expect(request.get).toHaveBeenCalledWith('/user/risk/export', { params: { format: 'pdf', days: 90 }, responseType: 'blob' })
    })
    it('exportUserRiskCsv 默认 days=90', async () => {
      (request.get as any).mockResolvedValueOnce({ data: new Blob() })
      await reportsApi.exportUserRiskCsv()
      expect(request.get).toHaveBeenCalledWith('/user/risk/export', { params: { format: 'csv', days: 90 }, responseType: 'blob' })
    })
    it('exportUserRiskJson 走 requestData 非 blob', async () => {
      (requestData as any).mockResolvedValueOnce({ points: [] })
      await reportsApi.exportUserRiskJson(30)
      expect(request.get).toHaveBeenCalledWith('/user/risk/export', { params: { format: 'json', days: 30 } })
    })
  })

  describe('管理员侧', () => {
    it('listReportTemplates 调 GET /reports/templates', async () => {
      (requestData as any).mockResolvedValueOnce({ templates: [], total: 0 })
      await reportsApi.listReportTemplates()
      expect(request.get).toHaveBeenCalledWith('/reports/templates')
    })
    it('generateUserRiskPdfSync POST /reports/user-risk/pdf 且 responseType=blob', async () => {
      (request.post as any).mockResolvedValueOnce({ data: new Blob() })
      await reportsApi.generateUserRiskPdfSync({ user_id: 1, user_name: 'x', risk_level: 2, risk_trend: 'stable', recommendations: [] })
      expect(request.post).toHaveBeenCalledWith('/reports/user-risk/pdf', { user_id: 1, user_name: 'x', risk_level: 2, risk_trend: 'stable', recommendations: [] }, { responseType: 'blob' })
    })
    it('generateUserRiskPdfAsync POST 返回 job_id', async () => {
      (requestData as any).mockResolvedValueOnce({ job_id: 'j1', status: 'queued', message: 'ok' })
      const res = await reportsApi.generateUserRiskPdfAsync({ user_id: 1, user_name: 'x', risk_level: 1, risk_trend: 'up', recommendations: [] })
      expect(res.job_id).toBe('j1')
    })
    it('getPdfJobStatus GET /reports/pdf/{id}/status', async () => {
      (requestData as any).mockResolvedValueOnce({ job_id: 'j1', status: 'completed', progress: 100 })
      await reportsApi.getPdfJobStatus('j1')
      expect(request.get).toHaveBeenCalledWith('/reports/pdf/j1/status')
    })
    it('downloadPdf GET /reports/pdf/{id}/download responseType=blob', async () => {
      (request.get as any).mockResolvedValueOnce({ data: new Blob() })
      await reportsApi.downloadPdf('j1')
      expect(request.get).toHaveBeenCalledWith('/reports/pdf/j1/download', { responseType: 'blob' })
    })
    it('listPdfJobs GET /reports/pdf/jobs', async () => {
      (requestData as any).mockResolvedValueOnce({ jobs: [], total: 0 })
      await reportsApi.listPdfJobs()
      expect(request.get).toHaveBeenCalledWith('/reports/pdf/jobs')
    })
    it('batchExportExcel POST /reports/batch-export/excel responseType=blob', async () => {
      (request.post as any).mockResolvedValueOnce({ data: new Blob() })
      await reportsApi.batchExportExcel({ data: [], columns: [], filename: 'r.xlsx' })
      expect(request.post).toHaveBeenCalledWith('/reports/batch-export/excel', { data: [], columns: [], filename: 'r.xlsx' }, { responseType: 'blob' })
    })
  })

  describe('celery 变体（仅接通）', () => {
    it('generateUserRiskPdfCeleryAsync POST celery-async', async () => {
      (requestData as any).mockResolvedValueOnce({ job_id: 'c1', status: 'queued', message: 'ok' })
      await reportsApi.generateUserRiskPdfCeleryAsync({ user_id: 1, user_name: 'x', risk_level: 1, risk_trend: 'up', recommendations: [] })
      expect(request.post).toHaveBeenCalledWith('/reports/user-risk/pdf/celery-async', expect.any(Object))
    })
    it('getCeleryPdfJobStatus GET celery status', async () => {
      (requestData as any).mockResolvedValueOnce({ status: 'running' })
      await reportsApi.getCeleryPdfJobStatus('c1')
      expect(request.get).toHaveBeenCalledWith('/reports/pdf/celery/c1/status')
    })
    it('downloadCeleryPdf GET celery download', async () => {
      (request.get as any).mockResolvedValueOnce({ data: new Blob() })
      await reportsApi.downloadCeleryPdf('c1')
      expect(request.get).toHaveBeenCalledWith('/reports/pdf/celery/c1/download', { responseType: 'blob' })
    })
  })
})

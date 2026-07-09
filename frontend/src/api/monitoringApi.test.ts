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
    (requestData as any).mockResolvedValueOnce({ total_requests: 100 })
    await monitoringApi.getDashboardSummary()
    expect(request.get).toHaveBeenCalledWith('/monitoring/dashboard-summary')
  })
  it('getModelSuccessRate 传 time range', async () => {
    (requestData as any).mockResolvedValueOnce({ rate: 0.95 })
    await monitoringApi.getModelSuccessRate({ start_time: 's', end_time: 'e' })
    expect(request.get).toHaveBeenCalledWith('/monitoring/model-success-rate', { params: { start_time: 's', end_time: 'e' } })
  })
  it('getFallbackStats', async () => {
    (requestData as any).mockResolvedValueOnce({ count: 5 })
    await monitoringApi.getFallbackStats()
    expect(request.get).toHaveBeenCalledWith('/monitoring/fallback-stats', { params: undefined })
  })
  it('getDriftAlerts', async () => {
    (requestData as any).mockResolvedValueOnce({ items: [] })
    await monitoringApi.getDriftAlerts()
    expect(request.get).toHaveBeenCalledWith('/monitoring/drift-alerts', { params: undefined })
  })
  it('getEngineSnapshot', async () => {
    (requestData as any).mockResolvedValueOnce({ engines: [] })
    await monitoringApi.getEngineSnapshot()
    expect(request.get).toHaveBeenCalledWith('/monitoring/engine-snapshot', { params: undefined })
  })
  it('getRequestDetailsList 传分页参数', async () => {
    (requestData as any).mockResolvedValueOnce({ items: [], total: 0 })
    await monitoringApi.getRequestDetailsList({ limit: 20, offset: 0 })
    expect(request.get).toHaveBeenCalledWith('/monitoring/request-details', { params: { limit: 20, offset: 0 } })
  })
  it('getRequestDetail GET /monitoring/request-details/{id}', async () => {
    (requestData as any).mockResolvedValueOnce({ log_id: 'l1' })
    await monitoringApi.getRequestDetail('l1')
    expect(request.get).toHaveBeenCalledWith('/monitoring/request-details/l1')
  })
})

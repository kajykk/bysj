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

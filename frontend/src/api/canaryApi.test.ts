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
    (requestData as any).mockResolvedValueOnce({ total: 1, limit: 50, offset: 0, items: [deploy] })
    const res = await canaryApi.listCanaryDeployments()
    expect(request.get).toHaveBeenCalledWith('/canary/deployments')
    expect(res.items).toHaveLength(1)
  })
  it('getCanaryDeployment GET /canary/deployments/{id}', async () => {
    (requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.getCanaryDeployment(1)
    expect(request.get).toHaveBeenCalledWith('/canary/deployments/1')
  })
  it('createCanaryDeployment POST', async () => {
    (requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.createCanaryDeployment({ version: 'v2', traffic_percent: 5 })
    expect(request.post).toHaveBeenCalledWith('/canary/deployments', { version: 'v2', traffic_percent: 5 })
  })
  it('updateCanaryTraffic PATCH /canary/deployments/{id}/traffic', async () => {
    (requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.updateCanaryTraffic(1, { traffic_percent: 10 })
    expect(request.patch).toHaveBeenCalledWith('/canary/deployments/1/traffic', { traffic_percent: 10 })
  })
  it('pauseCanary POST /pause', async () => {
    (requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.pauseCanary(1)
    expect(request.post).toHaveBeenCalledWith('/canary/deployments/1/pause')
  })
  it('resumeCanary POST /resume', async () => {
    (requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.resumeCanary(1)
    expect(request.post).toHaveBeenCalledWith('/canary/deployments/1/resume')
  })
  it('rollbackCanary POST /rollback 带 reason', async () => {
    (requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.rollbackCanary(1, { reason: 'error rate high' })
    expect(request.post).toHaveBeenCalledWith('/canary/deployments/1/rollback', { reason: 'error rate high' })
  })
  it('completeCanary POST /complete', async () => {
    (requestData as any).mockResolvedValueOnce(deploy)
    await canaryApi.completeCanary(1)
    expect(request.post).toHaveBeenCalledWith('/canary/deployments/1/complete')
  })
  it('getCanaryTrafficPercentages 返回可选项', async () => {
    (requestData as any).mockResolvedValueOnce({ percentages: [1, 5, 10, 25, 50, 100] })
    const res = await canaryApi.getCanaryTrafficPercentages()
    expect(request.get).toHaveBeenCalledWith('/canary/traffic-percentages')
    expect(res.percentages).toContain(5)
  })
})

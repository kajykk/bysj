import { beforeEach, describe, expect, it, vi } from 'vitest'

// 模拟 request 模块以隔离测试 killSwitchApi 的 URL/方法/参数构造
vi.mock('./request', () => ({
  default: {
    get: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config })),
    post: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
  },
  dedupedGet: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config })),
  requestData: vi.fn(async (promise: Promise<{ data: unknown }>) => {
    const response = await promise
    return response.data
  }),
}))

import request, { dedupedGet } from './request'
import { killSwitchApi, type KillSwitchState } from './killSwitchApi'

const SAMPLE: KillSwitchState = {
  paused: true,
  reason: 'major misjudgment',
  activated_by: 7,
  activated_at: '2026-10-01T12:00:00+00:00',
  updated_at: '2026-10-01T12:00:00+00:00',
  degraded: false,
  source: 'redis',
}

describe('api/killSwitchApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getStatus', () => {
    it('调用 GET /model-kill-switch/status', async () => {
      (request.get as any).mockResolvedValueOnce({ data: SAMPLE })
      const state = await killSwitchApi.getStatus()
      expect(request.get).toHaveBeenCalledWith('/model-kill-switch/status')
      expect(state).toEqual(SAMPLE)
    })

    it('不使用 dedupedGet（开关状态是安全相关实时值，不能被请求去重缓存）', async () => {
      (request.get as any).mockResolvedValueOnce({ data: SAMPLE })
      await killSwitchApi.getStatus()
      expect(dedupedGet).not.toHaveBeenCalled()
    })
  })

  describe('activate', () => {
    it('以 { reason } 调 POST /model-kill-switch/activate', async () => {
      (request.post as any).mockResolvedValueOnce({ data: SAMPLE })
      await killSwitchApi.activate('crisis event')
      expect(request.post).toHaveBeenCalledWith('/model-kill-switch/activate', {
        reason: 'crisis event',
      })
    })
  })

  describe('deactivate', () => {
    it('以 { reason } 调 POST /model-kill-switch/deactivate', async () => {
      (request.post as any).mockResolvedValueOnce({ data: { ...SAMPLE, paused: false } })
      await killSwitchApi.deactivate('resolved')
      expect(request.post).toHaveBeenCalledWith('/model-kill-switch/deactivate', {
        reason: 'resolved',
      })
    })
  })

  describe('状态契约', () => {
    it('degraded/source 字段必须透传（P1-7：区分「确认未暂停」与「不知道」）', async () => {
      const degraded: KillSwitchState = {
        ...SAMPLE,
        paused: true,
        degraded: true,
        source: 'unavailable',
      }
      ;(request.get as any).mockResolvedValueOnce({ data: degraded })
      const state = await killSwitchApi.getStatus()
      expect(state.degraded).toBe(true)
      expect(state.source).toBe('unavailable')
    })
  })
})

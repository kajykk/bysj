import { beforeEach, describe, expect, it, vi } from 'vitest'

// 模拟 request 模块以隔离测试 userInterventionApi
vi.mock('./request', () => ({
  default: {
    get: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config })),
    post: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
    put: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
    delete: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config }))
  },
  requestData: vi.fn(async (promise: Promise<{ data: unknown }>) => {
    const response = await promise
    return response.data
  }),
  requestPageData: vi.fn(async (promise: Promise<{ data: unknown }>) => {
    const response = await promise
    return response.data
  })
}))

import request, { requestData, requestPageData } from './request'
import { userInterventionApi } from './userInterventionApi'

describe('api/userInterventionApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getActiveIntervention', () => {
    it('调用 GET /user/intervention/active', async () => {
      (requestData as any).mockResolvedValueOnce({ plan: { id: 1, plan_name: 'P' }, tasks: [] })
      await userInterventionApi.getActiveIntervention()
      expect(request.get).toHaveBeenCalledWith('/user/intervention/active')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('404'))
      await expect(userInterventionApi.getActiveIntervention()).rejects.toThrow('404')
    })
  })

  describe('getInterventionHistory', () => {
    it('携带分页参数调用 GET /user/intervention/history', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 2, page_size: 20 })
      await userInterventionApi.getInterventionHistory({ page: 2, page_size: 20 })
      expect(request.get).toHaveBeenCalledWith('/user/intervention/history', {
        params: { page: 2, page_size: 20 }
      })
    })

    it('默认分页', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userInterventionApi.getInterventionHistory()
      expect(request.get).toHaveBeenCalledWith('/user/intervention/history', {
        params: { page: 1, page_size: 10 }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userInterventionApi.getInterventionHistory()).rejects.toThrow('500')
    })
  })

  describe('completeInterventionTask', () => {
    it('携带 scheduled_date 通过 PUT 完成任务', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      await userInterventionApi.completeInterventionTask(88, '2026-04-16')
      expect(request.put).toHaveBeenCalledWith('/user/intervention/tasks/88/complete', {
        scheduled_date: '2026-04-16'
      })
    })

    it('省略 scheduled_date 时为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userInterventionApi.completeInterventionTask(88)
      expect(request.put).toHaveBeenCalledWith('/user/intervention/tasks/88/complete', {
        scheduled_date: undefined
      })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('409'))
      await expect(userInterventionApi.completeInterventionTask(1)).rejects.toThrow('409')
    })
  })

  describe('feedbackInterventionTask', () => {
    it('携带评分 + 笔记通过 PUT 提交反馈', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      await userInterventionApi.feedbackInterventionTask(5, {
        scheduled_date: '2026-04-16',
        feedback_score: 4,
        feedback_note: 'good'
      })
      expect(request.put).toHaveBeenCalledWith('/user/intervention/tasks/5/feedback', {
        scheduled_date: '2026-04-16',
        feedback_score: 4,
        feedback_note: 'good'
      })
    })

    it('仅传部分字段时其他为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userInterventionApi.feedbackInterventionTask(5, { feedback_score: 2 })
      expect(request.put).toHaveBeenCalledWith('/user/intervention/tasks/5/feedback', {
        scheduled_date: undefined,
        feedback_score: 2,
        feedback_note: undefined
      })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('422'))
      await expect(userInterventionApi.feedbackInterventionTask(1, {})).rejects.toThrow('422')
    })
  })

  describe('skipInterventionTask', () => {
    it('携带 note 通过 PUT 跳过任务', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      await userInterventionApi.skipInterventionTask(5, { scheduled_date: '2026-04-16', note: 'busy' })
      expect(request.put).toHaveBeenCalledWith('/user/intervention/tasks/5/skip', {
        scheduled_date: '2026-04-16',
        note: 'busy'
      })
    })

    it('空 payload 时字段为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userInterventionApi.skipInterventionTask(5, {})
      expect(request.put).toHaveBeenCalledWith('/user/intervention/tasks/5/skip', {
        scheduled_date: undefined,
        note: undefined
      })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('409'))
      await expect(userInterventionApi.skipInterventionTask(1, {})).rejects.toThrow('409')
    })
  })

  describe('markInterventionTaskMissed', () => {
    it('通过 PUT /user/intervention/tasks/:id/missed 标记缺勤', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      await userInterventionApi.markInterventionTaskMissed(7, { scheduled_date: '2026-04-16', note: 'no show' })
      expect(request.put).toHaveBeenCalledWith('/user/intervention/tasks/7/missed', {
        scheduled_date: '2026-04-16',
        note: 'no show'
      })
    })

    it('空 payload 字段为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userInterventionApi.markInterventionTaskMissed(7, {})
      expect(request.put).toHaveBeenCalledWith('/user/intervention/tasks/7/missed', {
        scheduled_date: undefined,
        note: undefined
      })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('409'))
      await expect(userInterventionApi.markInterventionTaskMissed(1, {})).rejects.toThrow('409')
    })
  })

  describe('postponeInterventionTask', () => {
    it('携带 postpone_to + note 通过 PUT 推迟任务', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      await userInterventionApi.postponeInterventionTask(7, {
        scheduled_date: '2026-04-16',
        postpone_to: '2026-04-20',
        note: 'travel'
      })
      expect(request.put).toHaveBeenCalledWith('/user/intervention/tasks/7/postpone', {
        scheduled_date: '2026-04-16',
        postpone_to: '2026-04-20',
        note: 'travel'
      })
    })

    it('仅必填 postpone_to 字段时其他为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userInterventionApi.postponeInterventionTask(7, { postpone_to: '2026-04-20' })
      expect(request.put).toHaveBeenCalledWith('/user/intervention/tasks/7/postpone', {
        scheduled_date: undefined,
        postpone_to: '2026-04-20',
        note: undefined
      })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('422'))
      await expect(userInterventionApi.postponeInterventionTask(1, { postpone_to: 'x' })).rejects.toThrow('422')
    })
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'

// 模拟 request 模块以隔离测试 counselorApi 的 URL/方法/参数构造
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
import { counselorApi } from './counselorApi'

describe('api/counselorApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getCounselorWarnings', () => {
    it('携带分页 + only_unhandled 参数调用 GET /counselor/warnings', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await counselorApi.getCounselorWarnings({ page: 1, page_size: 10, only_unhandled: true })
      expect(request.get).toHaveBeenCalledWith('/counselor/warnings', {
        params: { page: 1, page_size: 10, only_unhandled: true, risk_level: undefined }
      })
    })

    it('默认分页 + only_unhandled=undefined', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await counselorApi.getCounselorWarnings()
      expect(request.get).toHaveBeenCalledWith('/counselor/warnings', {
        params: { page: 1, page_size: 10, only_unhandled: undefined, risk_level: undefined }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(counselorApi.getCounselorWarnings()).rejects.toThrow('500')
    })
  })

  describe('handleCounselorWarning', () => {
    it('通过 PUT /counselor/warnings/:id/handle 处理预警', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      const res = await counselorApi.handleCounselorWarning(55, 'handle', '已联系')
      expect(request.put).toHaveBeenCalledWith('/counselor/warnings/55/handle', {
        action: 'handle',
        note: '已联系'
      })
      expect(res).toEqual({ message: 'ok' })
    })

    it('note 省略时为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await counselorApi.handleCounselorWarning(7, 'ignore')
      expect(request.put).toHaveBeenCalledWith('/counselor/warnings/7/handle', {
        action: 'ignore',
        note: undefined
      })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('404'))
      await expect(counselorApi.handleCounselorWarning(1, 'handle')).rejects.toThrow('404')
    })
  })

  describe('getCounselorUsers', () => {
    it('携带 risk_level 过滤调用 GET /counselor/users', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await counselorApi.getCounselorUsers({ page: 2, page_size: 20, risk_level: 3 })
      expect(request.get).toHaveBeenCalledWith('/counselor/users', {
        params: { page: 2, page_size: 20, risk_level: 3 }
      })
    })

    it('默认分页 + risk_level=undefined', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await counselorApi.getCounselorUsers()
      expect(request.get).toHaveBeenCalledWith('/counselor/users', {
        params: { page: 1, page_size: 10, risk_level: undefined }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(counselorApi.getCounselorUsers()).rejects.toThrow('500')
    })
  })

  describe('getCounselorUserDetail', () => {
    it('调用 GET /counselor/users/:userId', async () => {
      (requestData as any).mockResolvedValueOnce({ id: 9, username: 'u' })
      await counselorApi.getCounselorUserDetail(9)
      expect(request.get).toHaveBeenCalledWith('/counselor/users/9')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('404'))
      await expect(counselorApi.getCounselorUserDetail(0)).rejects.toThrow('404')
    })
  })

  describe('getCounselorUserConsultations', () => {
    it('携带分页参数调用 GET /counselor/users/:userId/consultations', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await counselorApi.getCounselorUserConsultations(3, { page: 1, page_size: 5 })
      expect(request.get).toHaveBeenCalledWith('/counselor/users/3/consultations', {
        params: { page: 1, page_size: 5 }
      })
    })

    it('默认分页', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await counselorApi.getCounselorUserConsultations(3)
      expect(request.get).toHaveBeenCalledWith('/counselor/users/3/consultations', {
        params: { page: 1, page_size: 10 }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(counselorApi.getCounselorUserConsultations(1)).rejects.toThrow('500')
    })
  })

  describe('createCounselorUserConsultation', () => {
    it('通过 POST 创建咨询记录', async () => {
      (requestData as any).mockResolvedValueOnce({ id: 1 })
      await counselorApi.createCounselorUserConsultation(7, { main_topics: 'sleep' })
      expect(request.post).toHaveBeenCalledWith('/counselor/users/7/consultations', { main_topics: 'sleep' })
    })

    it('空对象 payload', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await counselorApi.createCounselorUserConsultation(7, {})
      expect(request.post).toHaveBeenCalledWith('/counselor/users/7/consultations', {})
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('422'))
      await expect(counselorApi.createCounselorUserConsultation(1, {})).rejects.toThrow('422')
    })
  })

  describe('updateCounselorUserConsultation', () => {
    it('通过 PUT 更新咨询记录', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      await counselorApi.updateCounselorUserConsultation(7, 100, { main_topics: 'X' })
      expect(request.put).toHaveBeenCalledWith('/counselor/users/7/consultations/100', { main_topics: 'X' })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('404'))
      await expect(counselorApi.updateCounselorUserConsultation(1, 1, {})).rejects.toThrow('404')
    })
  })

  describe('getCounselorGroups', () => {
    it('默认分页调用 GET /counselor/groups', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await counselorApi.getCounselorGroups()
      expect(request.get).toHaveBeenCalledWith('/counselor/groups', {
        params: { page: 1, page_size: 10 }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(counselorApi.getCounselorGroups()).rejects.toThrow('500')
    })
  })

  describe('createCounselorGroup', () => {
    it('通过 POST 创建小组', async () => {
      (requestData as any).mockResolvedValueOnce({ group_id: 42 })
      await counselorApi.createCounselorGroup({ group_name: 'A组', description: 'demo', color_tag: '#409EFF' })
      expect(request.post).toHaveBeenCalledWith('/counselor/groups', {
        group_name: 'A组',
        description: 'demo',
        color_tag: '#409EFF'
      })
    })

    it('仅必填字段', async () => {
      (requestData as any).mockResolvedValueOnce({ group_id: 1 })
      await counselorApi.createCounselorGroup({ group_name: 'B组' })
      expect(request.post).toHaveBeenCalledWith('/counselor/groups', {
        group_name: 'B组',
        description: undefined,
        color_tag: undefined
      })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('422'))
      await expect(counselorApi.createCounselorGroup({ group_name: '' })).rejects.toThrow('422')
    })
  })

  describe('addCounselorGroupMember', () => {
    it('通过 POST 添加成员', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      await counselorApi.addCounselorGroupMember(5, 12)
      expect(request.post).toHaveBeenCalledWith('/counselor/groups/5/members', { user_id: 12 })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('400'))
      await expect(counselorApi.addCounselorGroupMember(1, 1)).rejects.toThrow('400')
    })
  })

  describe('getCounselorUnhandledWarningCount', () => {
    it('成功时返回 total', async () => {
      (requestPageData as any).mockResolvedValueOnce({ total: 17, items: [], page: 1, page_size: 1 })
      const count = await counselorApi.getCounselorUnhandledWarningCount()
      expect(request.get).toHaveBeenCalledWith('/counselor/warnings', {
        params: { page: 1, page_size: 1, only_unhandled: true }
      })
      expect(count).toBe(17)
    })

    it('接口异常时返回 0', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      const count = await counselorApi.getCounselorUnhandledWarningCount()
      expect(count).toBe(0)
    })
  })

  describe('getCounselorUserCount', () => {
    it('成功时返回 total', async () => {
      (requestPageData as any).mockResolvedValueOnce({ total: 42, items: [], page: 1, page_size: 1 })
      const count = await counselorApi.getCounselorUserCount()
      expect(request.get).toHaveBeenCalledWith('/counselor/users', {
        params: { page: 1, page_size: 1 }
      })
      expect(count).toBe(42)
    })

    it('接口异常时返回 0', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      const count = await counselorApi.getCounselorUserCount()
      expect(count).toBe(0)
    })
  })

  describe('getCounselorBindCode', () => {
    it('调用 GET /counselor/bind-code', async () => {
      (requestData as any).mockResolvedValueOnce({ bind_code: 'ABC123' })
      await counselorApi.getCounselorBindCode()
      expect(request.get).toHaveBeenCalledWith('/counselor/bind-code')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(counselorApi.getCounselorBindCode()).rejects.toThrow('500')
    })
  })

  describe('refreshCounselorBindCode', () => {
    it('调用 POST /counselor/bind-code/refresh', async () => {
      (requestData as any).mockResolvedValueOnce({ bind_code: 'NEW' })
      await counselorApi.refreshCounselorBindCode()
      expect(request.post).toHaveBeenCalledWith('/counselor/bind-code/refresh')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(counselorApi.refreshCounselorBindCode()).rejects.toThrow('500')
    })
  })

  describe('getUserBinding', () => {
    it('调用 GET /user/data/binding', async () => {
      (requestData as any).mockResolvedValueOnce(null)
      await counselorApi.getUserBinding()
      expect(request.get).toHaveBeenCalledWith('/user/data/binding')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('401'))
      await expect(counselorApi.getUserBinding()).rejects.toThrow('401')
    })
  })

  describe('getReviews', () => {
    it('携带 status + priority 过滤调用 GET /reviews', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await counselorApi.getReviews({ page: 1, page_size: 10, status: 'open', priority: 'high' })
      expect(request.get).toHaveBeenCalledWith('/reviews', {
        params: { page: 1, page_size: 10, status: 'open', priority: 'high' }
      })
    })

    it('默认分页 + undefined 过滤', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await counselorApi.getReviews()
      expect(request.get).toHaveBeenCalledWith('/reviews', {
        params: { page: 1, page_size: 10, status: undefined, priority: undefined }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(counselorApi.getReviews()).rejects.toThrow('500')
    })
  })

  describe('getReviewStats', () => {
    it('调用 GET /reviews/stats', async () => {
      (requestData as any).mockResolvedValueOnce({ total: 0, open: 0, escalated: 0 })
      await counselorApi.getReviewStats()
      expect(request.get).toHaveBeenCalledWith('/reviews/stats')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(counselorApi.getReviewStats()).rejects.toThrow('500')
    })
  })

  describe('getReviewDetail', () => {
    it('调用 GET /reviews/:id', async () => {
      (requestData as any).mockResolvedValueOnce({ id: 5 })
      await counselorApi.getReviewDetail(5)
      expect(request.get).toHaveBeenCalledWith('/reviews/5')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('404'))
      await expect(counselorApi.getReviewDetail(99)).rejects.toThrow('404')
    })
  })

  describe('resolveReview', () => {
    it('通过 POST /reviews/:id/resolve 解决 review', async () => {
      (requestData as any).mockResolvedValueOnce({ id: 5, status: 'resolved' })
      await counselorApi.resolveReview(5, { resolution_note: 'handled' })
      expect(request.post).toHaveBeenCalledWith('/reviews/5/resolve', { resolution_note: 'handled' })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('409'))
      await expect(counselorApi.resolveReview(1, { resolution_note: 'x' })).rejects.toThrow('409')
    })
  })

  describe('escalateReview', () => {
    it('通过 POST /reviews/:id/escalate 升级 review', async () => {
      (requestData as any).mockResolvedValueOnce({ id: 5, status: 'escalated' })
      await counselorApi.escalateReview(5, { reason: 'high risk' })
      expect(request.post).toHaveBeenCalledWith('/reviews/5/escalate', { reason: 'high risk' })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('400'))
      await expect(counselorApi.escalateReview(1, { reason: 'x' })).rejects.toThrow('400')
    })
  })
})

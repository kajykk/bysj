import { beforeEach, describe, expect, it, vi } from 'vitest'

// 模拟 request 模块以隔离测试 userWarningsApi
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
import { userWarningsApi } from './userWarningsApi'

describe('api/userWarningsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getUserWarnings', () => {
    it('携带 is_read 过滤调用 GET /user/warnings', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userWarningsApi.getUserWarnings({ page: 1, page_size: 10, is_read: false })
      expect(request.get).toHaveBeenCalledWith('/user/warnings', {
        params: { page: 1, page_size: 10, is_read: false }
      })
    })

    it('默认分页 + is_read=undefined', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userWarningsApi.getUserWarnings()
      expect(request.get).toHaveBeenCalledWith('/user/warnings', {
        params: { page: 1, page_size: 10, is_read: undefined }
      })
    })

    it('is_read=true 仅获取已读', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userWarningsApi.getUserWarnings({ is_read: true })
      expect(request.get).toHaveBeenCalledWith('/user/warnings', {
        params: { page: 1, page_size: 10, is_read: true }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userWarningsApi.getUserWarnings()).rejects.toThrow('500')
    })
  })

  describe('markUserWarningRead', () => {
    it('通过 PUT /user/warnings/:id/read 标记已读', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      await userWarningsApi.markUserWarningRead(99)
      expect(request.put).toHaveBeenCalledWith('/user/warnings/99/read')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('404'))
      await expect(userWarningsApi.markUserWarningRead(0)).rejects.toThrow('404')
    })
  })

  describe('getUserAssessmentHistory', () => {
    it('携带 type + 日期范围 + 分页调用 GET /user/data/history', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userWarningsApi.getUserAssessmentHistory({
        page: 2,
        page_size: 20,
        type: 'structured',
        start_date: '2026-01-01',
        end_date: '2026-06-30'
      })
      expect(request.get).toHaveBeenCalledWith('/user/data/history', {
        params: {
          page: 2,
          page_size: 20,
          type: 'structured',
          start_date: '2026-01-01',
          end_date: '2026-06-30'
        }
      })
    })

    it('默认分页 + 全 undefined 过滤', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userWarningsApi.getUserAssessmentHistory()
      expect(request.get).toHaveBeenCalledWith('/user/data/history', {
        params: {
          page: 1,
          page_size: 10,
          type: undefined,
          start_date: undefined,
          end_date: undefined
        }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userWarningsApi.getUserAssessmentHistory()).rejects.toThrow('500')
    })
  })

  describe('getDataHistory', () => {
    it('携带 type 过滤调用 GET /user/data/history', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userWarningsApi.getDataHistory({ type: 'physiological', page: 1, page_size: 5 })
      expect(request.get).toHaveBeenCalledWith('/user/data/history', {
        params: { page: 1, page_size: 5, type: 'physiological' }
      })
    })

    it('默认分页 + type=undefined', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userWarningsApi.getDataHistory()
      expect(request.get).toHaveBeenCalledWith('/user/data/history', {
        params: { page: 1, page_size: 10, type: undefined }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userWarningsApi.getDataHistory()).rejects.toThrow('500')
    })
  })

  describe('getWarningSettings', () => {
    it('调用 GET /user/warning-settings', async () => {
      (requestData as any).mockResolvedValueOnce({
        notify_channels: { email: true },
        threshold_level: 2,
        quiet_hours_start: '22:00',
        quiet_hours_end: '07:00'
      })
      await userWarningsApi.getWarningSettings()
      expect(request.get).toHaveBeenCalledWith('/user/warning-settings')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userWarningsApi.getWarningSettings()).rejects.toThrow('500')
    })
  })

  describe('updateWarningSettings', () => {
    it('携带完整 payload 通过 PUT /user/warning-settings 提交', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok' })
      await userWarningsApi.updateWarningSettings({
        notify_channels: { email: true, sms: false },
        threshold_level: 3,
        quiet_hours_start: '22:00',
        quiet_hours_end: '07:00'
      })
      expect(request.put).toHaveBeenCalledWith('/user/warning-settings', {
        notify_channels: { email: true, sms: false },
        threshold_level: 3,
        quiet_hours_start: '22:00',
        quiet_hours_end: '07:00'
      })
    })

    it('notify_channels 缺失时归一化为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userWarningsApi.updateWarningSettings({ threshold_level: 1 })
      expect(request.put).toHaveBeenCalledWith('/user/warning-settings', {
        notify_channels: undefined,
        threshold_level: 1,
        quiet_hours_start: undefined,
        quiet_hours_end: undefined
      })
    })

    it('notify_channels=null 时归一化为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userWarningsApi.updateWarningSettings({
        notify_channels: null as unknown as Record<string, boolean>,
        threshold_level: 1
      })
      expect(request.put).toHaveBeenCalledWith('/user/warning-settings', {
        notify_channels: undefined,
        threshold_level: 1,
        quiet_hours_start: undefined,
        quiet_hours_end: undefined
      })
    })

    it('quiet_hours 空字符串时归一化为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userWarningsApi.updateWarningSettings({
        threshold_level: 1,
        quiet_hours_start: '',
        quiet_hours_end: ''
      })
      expect(request.put).toHaveBeenCalledWith('/user/warning-settings', {
        notify_channels: undefined,
        threshold_level: 1,
        quiet_hours_start: undefined,
        quiet_hours_end: undefined
      })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('422'))
      await expect(
        userWarningsApi.updateWarningSettings({ threshold_level: 1 })
      ).rejects.toThrow('422')
    })
  })

  describe('markAllWarningsRead', () => {
    it('通过 PUT /user/warnings/read-all 标记全部已读', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'ok', count: 5 })
      const res = await userWarningsApi.markAllWarningsRead()
      expect(request.put).toHaveBeenCalledWith('/user/warnings/read-all')
      expect(res).toEqual({ message: 'ok', count: 5 })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userWarningsApi.markAllWarningsRead()).rejects.toThrow('500')
    })
  })
})

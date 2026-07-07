import { beforeEach, describe, expect, it, vi } from 'vitest'

// 模拟 request 模块：所有 HTTP 方法返回伪 response，requestData/requestPageData 解包 data
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
import { adminApi } from './adminApi'

describe('api/adminApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('listAdminTemplates', () => {
    it('默认分页参数调用 GET /admin/templates', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await adminApi.listAdminTemplates()
      expect(request.get).toHaveBeenCalledWith('/admin/templates', {
        params: { page: 1, page_size: 10 }
      })
    })

    it('携带显式分页参数', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 2, page_size: 20 })
      await adminApi.listAdminTemplates({ page: 2, page_size: 20 })
      expect(request.get).toHaveBeenCalledWith('/admin/templates', {
        params: { page: 2, page_size: 20 }
      })
    })

    it('接口错误时透传异常', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(adminApi.listAdminTemplates()).rejects.toThrow('500')
    })
  })

  describe('upsertAdminTemplate', () => {
    it('通过 POST /admin/templates 创建模板', async () => {
      (requestData as any).mockResolvedValueOnce({ template_id: 7 })
      const res = await adminApi.upsertAdminTemplate({
        template_name: '基础方案',
        applicable_levels: [1, 2],
        task_list: [{ task_name: '呼吸训练', task_type: 'meditation' }]
      })

      expect(request.post).toHaveBeenCalledWith('/admin/templates', {
        template_name: '基础方案',
        applicable_levels: [1, 2],
        task_list: [{ task_name: '呼吸训练', task_type: 'meditation' }]
      })
      expect(res).toEqual({ template_id: 7 })
    })

    it('携带可选字段（estimated_weeks/status/description/schedule）', async () => {
      (requestData as any).mockResolvedValueOnce({ template_id: 1 })
      await adminApi.upsertAdminTemplate({
        id: 5,
        template_name: '完整',
        applicable_levels: [3],
        task_list: [{
          task_name: '冥想',
          task_type: 'meditation',
          description: 'desc',
          schedule: 'daily',
          duration_minutes: 30,
          sort_order: 1
        }],
        estimated_weeks: 4,
        status: 'inactive'
      })
      expect(request.post).toHaveBeenCalledWith('/admin/templates', {
        id: 5,
        template_name: '完整',
        applicable_levels: [3],
        task_list: [{
          task_name: '冥想',
          task_type: 'meditation',
          description: 'desc',
          schedule: 'daily',
          duration_minutes: 30,
          sort_order: 1
        }],
        estimated_weeks: 4,
        status: 'inactive'
      })
    })

    it('空 task_list 仍按原样提交', async () => {
      (requestData as any).mockResolvedValueOnce({ template_id: 0 })
      await adminApi.upsertAdminTemplate({
        template_name: '空',
        applicable_levels: [],
        task_list: []
      })
      expect(request.post).toHaveBeenCalledWith('/admin/templates', {
        template_name: '空',
        applicable_levels: [],
        task_list: []
      })
    })

    it('提交失败时抛出错误', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('422'))
      await expect(
        adminApi.upsertAdminTemplate({ template_name: 'x', applicable_levels: [], task_list: [] })
      ).rejects.toThrow('422')
    })
  })

  describe('listAdminThresholds', () => {
    it('调用 GET /admin/thresholds', async () => {
      (requestData as any).mockResolvedValueOnce({ items: [] })
      await adminApi.listAdminThresholds()
      expect(request.get).toHaveBeenCalledWith('/admin/thresholds')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(adminApi.listAdminThresholds()).rejects.toThrow('500')
    })
  })

  describe('upsertAdminThreshold', () => {
    it('通过 POST /admin/thresholds 提交阈值', async () => {
      (requestData as any).mockResolvedValueOnce({ threshold_id: 3 })
      const res = await adminApi.upsertAdminThreshold({
        level: 2,
        level_name: '中度',
        min_score: 40,
        max_score: 60,
        color: '#e6a23c',
        action_required: '重点关注'
      })
      expect(request.post).toHaveBeenCalledWith('/admin/thresholds', {
        level: 2,
        level_name: '中度',
        min_score: 40,
        max_score: 60,
        color: '#e6a23c',
        action_required: '重点关注'
      })
      expect(res).toEqual({ threshold_id: 3 })
    })

    it('接口报错时抛出', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('400'))
      await expect(
        adminApi.upsertAdminThreshold({
          level: 1,
          level_name: '低',
          min_score: 0,
          max_score: 30,
          color: '#67c23a',
          action_required: '观察'
        })
      ).rejects.toThrow('400')
    })
  })

  describe('listAdminConfigs', () => {
    it('调用 GET /admin/configs', async () => {
      (requestData as any).mockResolvedValueOnce({ items: [] })
      await adminApi.listAdminConfigs()
      expect(request.get).toHaveBeenCalledWith('/admin/configs')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(adminApi.listAdminConfigs()).rejects.toThrow('500')
    })
  })

  describe('upsertAdminConfig', () => {
    it('通过 POST /admin/configs 提交配置', async () => {
      (requestData as any).mockResolvedValueOnce({ config_id: 11 })
      const res = await adminApi.upsertAdminConfig({
        config_key: 'system.notice',
        config_value: { enabled: true },
        description: '公告开关'
      })
      expect(request.post).toHaveBeenCalledWith('/admin/configs', {
        config_key: 'system.notice',
        config_value: { enabled: true },
        description: '公告开关'
      })
      expect(res).toEqual({ config_id: 11 })
    })

    it('不携带可选 description 字段时为 undefined', async () => {
      (requestData as any).mockResolvedValueOnce({ config_id: 1 })
      await adminApi.upsertAdminConfig({ config_key: 'k', config_value: {} })
      expect(request.post).toHaveBeenCalledWith('/admin/configs', {
        config_key: 'k',
        config_value: {},
        description: undefined
      })
    })

    it('提交失败抛出', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('422'))
      await expect(
        adminApi.upsertAdminConfig({ config_key: 'k', config_value: {} })
      ).rejects.toThrow('422')
    })
  })

  describe('listAdminFeedbacks', () => {
    it('携带默认分页参数调用 GET /admin/model-feedbacks', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await adminApi.listAdminFeedbacks()
      expect(request.get).toHaveBeenCalledWith('/admin/model-feedbacks', {
        params: { page: 1, page_size: 10 }
      })
    })

    it('携带显式分页参数', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 5, page_size: 50 })
      await adminApi.listAdminFeedbacks({ page: 5, page_size: 50 })
      expect(request.get).toHaveBeenCalledWith('/admin/model-feedbacks', {
        params: { page: 5, page_size: 50 }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(adminApi.listAdminFeedbacks()).rejects.toThrow('500')
    })
  })

  describe('listAdminOperationLogs', () => {
    it('默认分页 + 全 undefined 过滤字段', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await adminApi.listAdminOperationLogs()
      expect(request.get).toHaveBeenCalledWith('/admin/operation-logs', {
        params: {
          page: 1,
          page_size: 10,
          action_type: undefined,
          operator_role: undefined,
          start_time: undefined,
          end_time: undefined
        }
      })
    })

    it('携带完整过滤参数', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await adminApi.listAdminOperationLogs({
        action_type: 'login',
        operator_role: 'admin',
        start_time: '2026-01-01',
        end_time: '2026-01-31',
        page: 2,
        page_size: 20
      })
      expect(request.get).toHaveBeenCalledWith('/admin/operation-logs', {
        params: {
          page: 2,
          page_size: 20,
          action_type: 'login',
          operator_role: 'admin',
          start_time: '2026-01-01',
          end_time: '2026-01-31'
        }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(adminApi.listAdminOperationLogs()).rejects.toThrow('500')
    })
  })

  describe('getAdminStats', () => {
    it('调用 GET /admin/stats 并解包统计数据', async () => {
      const stats = {
        total_users: 100,
        total_counselors: 5,
        today_warnings: 8,
        today_unhandled_warnings: 3,
        total_assessments: 200,
        high_risk_users: 7,
        total_templates: 4,
        active_templates: 2,
        yesterday_users: 95,
        yesterday_warnings: 6,
        yesterday_assessments: 180,
        yesterday_templates: 4
      }
      ;(requestData as any).mockResolvedValueOnce(stats)
      const res = await adminApi.getAdminStats()
      expect(request.get).toHaveBeenCalledWith('/admin/stats')
      expect(res).toEqual(stats)
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(adminApi.getAdminStats()).rejects.toThrow('500')
    })
  })

  describe('getHealthStatus', () => {
    it('调用 GET /health', async () => {
      (requestData as any).mockResolvedValueOnce({ status: 'ok', checks: { db: 'up' } })
      const res = await adminApi.getHealthStatus()
      expect(request.get).toHaveBeenCalledWith('/health')
      expect(res).toEqual({ status: 'ok', checks: { db: 'up' } })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('503'))
      await expect(adminApi.getHealthStatus()).rejects.toThrow('503')
    })
  })

  describe('getCrisisEvents', () => {
    it('默认分页 + undefined 过滤', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await adminApi.getCrisisEvents()
      expect(request.get).toHaveBeenCalledWith('/reviews/crisis-events', {
        params: {
          page: 1,
          page_size: 10,
          status: undefined,
          start_date: undefined,
          end_date: undefined
        }
      })
    })

    it('携带 status + 日期范围 + 分页', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await adminApi.getCrisisEvents({
        status: 'open',
        start_date: '2026-01-01',
        end_date: '2026-06-30',
        page: 1,
        page_size: 50
      })
      expect(request.get).toHaveBeenCalledWith('/reviews/crisis-events', {
        params: {
          page: 1,
          page_size: 50,
          status: 'open',
          start_date: '2026-01-01',
          end_date: '2026-06-30'
        }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(adminApi.getCrisisEvents()).rejects.toThrow('500')
    })
  })

  describe('exportCrisisEvents', () => {
    it('GET /admin/crisis-events/export 返回 Blob', async () => {
      const blob = new Blob(['data'], { type: 'text/csv' })
      ;(request.get as any).mockResolvedValueOnce({ data: blob })
      const res = await adminApi.exportCrisisEvents('2026-01-01', '2026-01-31')

      expect(request.get).toHaveBeenCalledWith('/admin/crisis-events/export', {
        params: { start_date: '2026-01-01', end_date: '2026-01-31' },
        responseType: 'blob'
      })
      expect(res).toBeInstanceOf(Blob)
    })

    it('导出失败抛出错误', async () => {
      (request.get as any).mockRejectedValueOnce(new Error('500'))
      await expect(adminApi.exportCrisisEvents('a', 'b')).rejects.toThrow('500')
    })
  })
})

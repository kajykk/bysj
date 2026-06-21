import { beforeEach, describe, expect, it, vi } from 'vitest'

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

import request from './request'
import { authApi } from './auth'
import { adminApi } from './adminApi'
import { buildPageParams } from './business.shared'
import { counselorApi } from './counselorApi'
import { userApi } from './userApi'

describe('domain API modules', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('builds user content requests through the user api', async () => {
    await userApi.listContents({ page: 2, page_size: 20, category: 'stress' })
    expect(request.get).toHaveBeenCalledWith('/user/content/', {
      params: { page: 2, page_size: 20, category: 'stress', content_type: undefined, keyword: undefined }
    })
  })

  it('builds counselor warning requests through the counselor api', async () => {
    await counselorApi.getCounselorWarnings({ page: 1, page_size: 10, only_unhandled: true })
    expect(request.get).toHaveBeenCalledWith('/counselor/warnings', {
      params: { page: 1, page_size: 10, only_unhandled: true, risk_level: undefined }
    })
  })

  it('builds admin settings requests through the admin api', async () => {
    await adminApi.listAdminConfigs()
    expect(request.get).toHaveBeenCalledWith('/admin/configs')
  })

  it('builds auth login requests through the auth api', async () => {
    await authApi.login({ username: 'demo', password: 'secret' })
    expect(request.post).toHaveBeenCalledWith('/auth/login', { username: 'demo', password: 'secret' })
  })

  it('sends user favorites actions through the user api', async () => {
    await userApi.toggleFavorite(12)
    expect(request.post).toHaveBeenCalledWith('/user/content/12/favorite')
  })

  it('sends intervention completion through the user api', async () => {
    await userApi.completeInterventionTask(88, '2026-04-16')
    expect(request.put).toHaveBeenCalledWith('/user/intervention/tasks/88/complete', { scheduled_date: '2026-04-16' })
  })

  it('creates counselor consultation records through the counselor api', async () => {
    await counselorApi.createCounselorUserConsultation(7, { main_topics: 'sleep' })
    expect(request.post).toHaveBeenCalledWith('/counselor/users/7/consultations', { main_topics: 'sleep' })
  })

  it('creates counselor groups through the counselor api', async () => {
    await counselorApi.createCounselorGroup({ group_name: 'A组', description: 'demo', color_tag: '#409EFF' })
    expect(request.post).toHaveBeenCalledWith('/counselor/groups', { group_name: 'A组', description: 'demo', color_tag: '#409EFF' })
  })

  it('handles warnings through the counselor api', async () => {
    await counselorApi.handleCounselorWarning(55, 'ignore', 'duplicate')
    expect(request.put).toHaveBeenCalledWith('/counselor/warnings/55/handle', { action: 'ignore', note: 'duplicate' })
  })

  it('upserts admin template payloads through the admin api', async () => {
    await adminApi.upsertAdminTemplate({
      template_name: '基础方案',
      applicable_levels: [1, 2],
      task_list: [{ task_name: '呼吸训练', task_type: 'meditation' }]
    })
    expect(request.post).toHaveBeenCalledWith('/admin/templates', {
      template_name: '基础方案',
      applicable_levels: [1, 2],
      task_list: [{ task_name: '呼吸训练', task_type: 'meditation' }]
    })
  })

  it('upserts admin threshold payloads through the admin api', async () => {
    await adminApi.upsertAdminThreshold({
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
  })

  it('upserts admin config payloads through the admin api', async () => {
    await adminApi.upsertAdminConfig({ config_key: 'system.notice', config_value: { enabled: true }, description: '公告开关' })
    expect(request.post).toHaveBeenCalledWith('/admin/configs', {
      config_key: 'system.notice',
      config_value: { enabled: true },
      description: '公告开关'
    })
  })

  it('builds default paging params consistently', () => {
    expect(buildPageParams()).toEqual({ page: 1, page_size: 10 })
  })

  it('builds explicit paging params consistently', () => {
    expect(buildPageParams({ page: 3, page_size: 25 })).toEqual({ page: 3, page_size: 25 })
  })

  it('requests password reset with body', async () => {
    await authApi.requestPasswordReset('demo@example.com')
    expect(request.post).toHaveBeenCalledWith('/auth/request-reset', { email: 'demo@example.com' })
  })

  it('requests risk export with pdf params', async () => {
    await userApi.exportRiskPdf(30)
    expect(request.get).toHaveBeenCalledWith('/user/risk/export', { params: { format: 'pdf', days: 30 }, responseType: 'blob' })
  })

  it('fetches counselor bind code through the counselor api', async () => {
    await counselorApi.getCounselorBindCode()
    expect(request.get).toHaveBeenCalledWith('/counselor/bind-code')
  })

  it('fetches admin operation logs through the admin api', async () => {
    await adminApi.listAdminOperationLogs({ action_type: 'login', operator_role: 'admin' })
    expect(request.get).toHaveBeenCalledWith('/admin/operation-logs', {
      params: {
        page: 1,
        page_size: 10,
        action_type: 'login',
        operator_role: 'admin',
        start_time: undefined,
        end_time: undefined
      }
    })
  })
})

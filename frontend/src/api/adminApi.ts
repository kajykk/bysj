import request, { requestData, requestPageData } from './request'
import { buildPageParams } from './business.shared'
import type { PageQuery } from '@/types/api'
import type { ConfigItem, CrisisEventItem, ModelFeedbackItem, OperationLogItem, TemplateItem, ThresholdItem } from './adminTypes'
import type { TaskType } from './taskTypes'

export type { ConfigItem, CrisisEventItem, ModelFeedbackItem, OperationLogItem, TemplateItem, ThresholdItem } from './adminTypes'

export const adminApi = {
  listAdminTemplates: (query?: PageQuery) => requestPageData<TemplateItem>(request.get('/admin/templates', { params: buildPageParams(query) })),

  upsertAdminTemplate: (payload: {
    id?: number
    template_name: string
    applicable_levels: number[]
    task_list: Array<{
      task_name: string
      task_type: TaskType
      description?: string | null
      schedule?: 'daily' | 'weekly' | 'monthly' | 'once' | 'manual' | null
      duration_minutes?: number | null
      sort_order?: number | null
    }>
    estimated_weeks?: number | null
    status?: 'active' | 'inactive'
  }) =>
    requestData<{ template_id: number }>(request.post('/admin/templates', payload)),

  // ISS-075: 删除干预模板
  deleteAdminTemplate: (templateId: number) =>
    requestData<{ message: string }>(request.delete(`/admin/templates/${templateId}`)),

  listAdminThresholds: () => requestData<{ items: ThresholdItem[] }>(request.get('/admin/thresholds')),

  upsertAdminThreshold: (payload: Omit<ThresholdItem, 'id'>) => requestData<{ threshold_id: number }>(request.post('/admin/thresholds', payload)),

  listAdminConfigs: () => requestData<{ items: ConfigItem[] }>(request.get('/admin/configs')),

  upsertAdminConfig: (payload: { config_key: string; config_value: Record<string, unknown>; description?: string }) =>
    requestData<{ config_id: number }>(request.post('/admin/configs', payload)),

  listAdminFeedbacks: (query?: PageQuery) => requestPageData<ModelFeedbackItem>(request.get('/admin/model-feedbacks', { params: buildPageParams(query) })),

  listAdminOperationLogs: (query?: PageQuery & { action_type?: string; operator_role?: string; start_time?: string; end_time?: string }) =>
    requestPageData<OperationLogItem>(request.get('/admin/operation-logs', {
      params: { ...buildPageParams(query), action_type: query?.action_type, operator_role: query?.operator_role, start_time: query?.start_time, end_time: query?.end_time }
    })),

  // ISS-080: 导出全部筛选条件下的操作日志（不分页）
  exportAdminOperationLogs: (query?: { action_type?: string; operator_role?: string; start_time?: string; end_time?: string }) =>
    requestData<{ items: OperationLogItem[]; total: number }>(request.get('/admin/operation-logs/export', {
      params: { action_type: query?.action_type, operator_role: query?.operator_role, start_time: query?.start_time, end_time: query?.end_time }
    })),

  getAdminStats: () => requestData<{
    total_users: number
    total_counselors: number
    today_warnings: number
    today_unhandled_warnings: number
    total_assessments: number
    high_risk_users: number
    total_templates: number
    active_templates: number
    // H-9 修复：补充 yesterday_* 字段，供 AdminDashboard 计算环比趋势
    yesterday_users: number
    yesterday_warnings: number
    yesterday_assessments: number
    yesterday_templates: number
  }>(request.get('/admin/stats')),

  getHealthStatus: () => requestData<{ status: string; checks: Record<string, string> }>(request.get('/health')),

  getCrisisEvents: (query?: PageQuery & { status?: string; start_date?: string; end_date?: string }) =>
    requestPageData<CrisisEventItem>(request.get('/reviews/crisis-events', {
      params: {
        ...buildPageParams(query),
        status: query?.status,
        start_date: query?.start_date,
        end_date: query?.end_date
      }
    })),

  exportCrisisEvents: (startDate: string, endDate: string): Promise<Blob> =>
    request
      .get('/admin/crisis-events/export', {
        params: { start_date: startDate, end_date: endDate },
        responseType: 'blob'
      })
      .then((res) => res.data as Blob),

  // ISS-072 修复：危机事件状态流转（处理 / 升级 / 关闭）
  handleCrisisEvent: (eventId: number, payload: { action: string; note?: string | null }) =>
    requestData<CrisisEventItem>(request.post(`/reviews/crisis-events/${eventId}/handle`, payload)),

  escalateCrisisEvent: (eventId: number, payload: { reason: string }) =>
    requestData<CrisisEventItem>(request.post(`/reviews/crisis-events/${eventId}/escalate`, payload)),

  closeCrisisEvent: (eventId: number, payload: { note?: string | null }) =>
    requestData<CrisisEventItem>(request.post(`/reviews/crisis-events/${eventId}/close`, payload)),

  // ISS-074 修复：管理员 GDPR 端点（导出 / 匿名化任意用户）
  exportUserGdpr: (userId: number): Promise<Blob> =>
    request
      .get(`/admin/gdpr/export/${userId}`, { responseType: 'blob' })
      .then((res) => res.data as Blob),

  deleteUserGdpr: (userId: number, payload: { confirm: boolean; reason: string }) =>
    requestData<Record<string, unknown>>(
      request.post(`/admin/gdpr/delete/${userId}`, payload)
    ),
}

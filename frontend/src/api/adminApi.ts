import request, { requestData, requestPageData } from './request'
import { buildPageParams } from './business.shared'
import type { PageQuery } from '@/types/api'
import type { ConfigItem, ModelFeedbackItem, OperationLogItem, TemplateItem, ThresholdItem } from './adminTypes'
import type { TaskType } from './taskTypes'

export type { ConfigItem, ModelFeedbackItem, OperationLogItem, TemplateItem, ThresholdItem } from './adminTypes'

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

  getAdminStats: () => requestData<{
    total_users: number
    total_counselors: number
    today_warnings: number
    today_unhandled_warnings: number
    total_assessments: number
    high_risk_users: number
    total_templates: number
    active_templates: number
  }>(request.get('/admin/stats')),

  getHealthStatus: () => requestData<{ status: string; checks: Record<string, string> }>(request.get('/health')),
}

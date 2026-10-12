import request, { dedupedGet, requestData, requestPageData } from './request'
import { buildPageParams } from './business.shared'
import type { PageQuery } from '@/types/api'
import type { ActiveIntervention, InterventionHistoryItem } from './userRiskApi'

export interface InterventionTaskItem {
  id: number
  task_name: string
  task_type: string
  description: string
  schedule: string
  duration_minutes: number
  today_status: 'pending' | 'completed' | 'missed' | 'skipped' | 'postponed'
  feedback_score: number | null
  feedback_note: string | null
}

/**
 * 干预计划统计（GET /user/intervention/stats，P1-15 / F-03）。
 *
 * SQL 层聚合，口径同 getInterventionHistory：avg_completion 为全部计划
 * 完成率（已完成执行数 / 任务总数 × 100，无任务计划记 0）的算术平均，
 * 四舍五入为整数百分比。
 */
export interface InterventionStats {
  active: number
  completed: number
  cancelled: number
  avg_completion: number
}

export const userInterventionApi = {
  getActiveIntervention: () => requestData<ActiveIntervention>(dedupedGet('/user/intervention/active')),
  getInterventionHistory: (query?: PageQuery) => requestPageData<InterventionHistoryItem>(dedupedGet('/user/intervention/history', { params: buildPageParams(query) })),
  // P1-15 / F-03: 干预计划统计（SQL 层聚合）。原实现 page_size:200 拉全量到
  // 前端 filter，计划超 200 条时分子截断、分母不截断，统计结果是错的。
  getInterventionStats: () => requestData<InterventionStats>(dedupedGet('/user/intervention/stats')),
  completeInterventionTask: (taskId: number, scheduledDate?: string) => requestData<{ message: string }>(request.put(`/user/intervention/tasks/${taskId}/complete`, { scheduled_date: scheduledDate })),
  feedbackInterventionTask: (taskId: number, payload: { scheduled_date?: string; feedback_score?: number; feedback_note?: string }) => requestData<{ message: string }>(request.put(`/user/intervention/tasks/${taskId}/feedback`, payload)),
  skipInterventionTask: (taskId: number, payload: { scheduled_date?: string; note?: string }) => requestData<{ message: string }>(request.put(`/user/intervention/tasks/${taskId}/skip`, payload)),
  // 功能完整性修复：补充 missed 状态标记方法，对应后端 PUT /user/intervention/tasks/{task_id}/missed
  markInterventionTaskMissed: (taskId: number, payload: { scheduled_date?: string; note?: string }) => requestData<{ message: string }>(request.put(`/user/intervention/tasks/${taskId}/missed`, payload)),
  postponeInterventionTask: (taskId: number, payload: { scheduled_date?: string; postpone_to: string; note?: string }) => requestData<{ message: string }>(request.put(`/user/intervention/tasks/${taskId}/postpone`, payload)),
}

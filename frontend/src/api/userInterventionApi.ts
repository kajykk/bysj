import request, { requestData, requestPageData } from './request'
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

export const userInterventionApi = {
  getActiveIntervention: () => requestData<ActiveIntervention>(request.get('/user/intervention/active')),
  getInterventionHistory: (query?: PageQuery) => requestPageData<InterventionHistoryItem>(request.get('/user/intervention/history', { params: buildPageParams(query) })),
  completeInterventionTask: (taskId: number, scheduledDate?: string) => requestData<{ message: string }>(request.put(`/user/intervention/tasks/${taskId}/complete`, { scheduled_date: scheduledDate })),
  feedbackInterventionTask: (taskId: number, payload: { scheduled_date?: string; feedback_score?: number; feedback_note?: string }) => requestData<{ message: string }>(request.put(`/user/intervention/tasks/${taskId}/feedback`, payload)),
  skipInterventionTask: (taskId: number, payload: { scheduled_date?: string; note?: string }) => requestData<{ message: string }>(request.put(`/user/intervention/tasks/${taskId}/skip`, payload)),
  // 功能完整性修复：补充 missed 状态标记方法，对应后端 PUT /user/intervention/tasks/{task_id}/missed
  markInterventionTaskMissed: (taskId: number, payload: { scheduled_date?: string; note?: string }) => requestData<{ message: string }>(request.put(`/user/intervention/tasks/${taskId}/missed`, payload)),
  postponeInterventionTask: (taskId: number, payload: { scheduled_date?: string; postpone_to: string; note?: string }) => requestData<{ message: string }>(request.put(`/user/intervention/tasks/${taskId}/postpone`, payload)),
}

import request, { requestData, requestPageData } from './request'
import { buildPageParams } from './business.shared'
import type { PageQuery } from '@/types/api'
import type { WarningItem, UserBindingInfo } from './userTypes'
import type { ConsultationGroupItem, ConsultationItem, ReviewItem, ReviewStats, UserManageItem } from './counselorTypes'

export type { WarningItem, UserBindingInfo } from './userTypes'
export type { ConsultationGroupItem, ConsultationItem, ReviewItem, ReviewStats, UserManageItem, UserRiskHistoryItem, UserAssessmentItem, UserInterventionItem } from './counselorTypes'

export const counselorApi = {
  getCounselorWarnings: (query?: PageQuery & { only_unhandled?: boolean }) =>
    requestPageData<WarningItem>(request.get('/counselor/warnings', { params: { ...buildPageParams(query), only_unhandled: query?.only_unhandled } })),

  handleCounselorWarning: (warningId: number, action: 'handle' | 'ignore', note?: string) =>
    requestData<{ message: string }>(request.put(`/counselor/warnings/${warningId}/handle`, { action, note })),

  // ISS-058: 升级预警
  escalateCounselorWarning: (warningId: number, payload: { reason: string }) =>
    requestData<{ message: string }>(request.put(`/counselor/warnings/${warningId}/escalate`, payload)),

  getCounselorUsers: (query?: PageQuery & { risk_level?: number }) =>
    requestPageData<UserManageItem>(request.get('/counselor/users', { params: { ...buildPageParams(query), risk_level: query?.risk_level } })),

  getCounselorUserDetail: (userId: number) => requestData<UserManageItem>(request.get(`/counselor/users/${userId}`)),

  getCounselorUserConsultations: (userId: number, query?: PageQuery) =>
    requestPageData<ConsultationItem>(request.get(`/counselor/users/${userId}/consultations`, { params: buildPageParams(query) })),

  createCounselorUserConsultation: (userId: number, payload: Partial<ConsultationItem>) =>
    requestData<ConsultationItem>(request.post(`/counselor/users/${userId}/consultations`, payload)),

  updateCounselorUserConsultation: (userId: number, recordId: number, payload: Partial<ConsultationItem>) =>
    requestData<{ message: string }>(request.put(`/counselor/users/${userId}/consultations/${recordId}`, payload)),

  getCounselorGroups: (query?: PageQuery) => requestPageData<ConsultationGroupItem>(request.get('/counselor/groups', { params: buildPageParams(query) })),

  createCounselorGroup: (payload: { group_name: string; description?: string; color_tag?: string }) =>
    requestData<{ group_id: number }>(request.post('/counselor/groups', payload)),

  addCounselorGroupMember: (groupId: number, userId: number) =>
    requestData<{ message: string }>(request.post(`/counselor/groups/${groupId}/members`, { user_id: userId })),

  getCounselorUnhandledWarningCount: async (): Promise<number> => {
    try {
      const data = await requestPageData<WarningItem>(request.get('/counselor/warnings', { params: { page: 1, page_size: 1, only_unhandled: true } }))
      return data.total
    } catch {
      return 0
    }
  },

  getCounselorUserCount: async (): Promise<number> => {
    try {
      const data = await requestPageData<UserManageItem>(request.get('/counselor/users', { params: { page: 1, page_size: 1 } }))
      return data.total
    } catch {
      return 0
    }
  },

  getCounselorBindCode: () => requestData<{ bind_code: string }>(request.get('/counselor/bind-code')),

  refreshCounselorBindCode: () => requestData<{ bind_code: string }>(request.post('/counselor/bind-code/refresh')),

  getUserBinding: () => requestData<UserBindingInfo | null>(request.get('/user/data/binding')),

  getReviews: (query?: PageQuery & { status?: string; priority?: string }) =>
    requestPageData<ReviewItem>(request.get('/reviews', {
      params: { ...buildPageParams(query), status: query?.status, priority: query?.priority }
    })),

  getReviewStats: () => requestData<ReviewStats>(request.get('/reviews/stats')),

  getReviewDetail: (id: number) => requestData<ReviewItem>(request.get(`/reviews/${id}`)),

  resolveReview: (id: number, payload: { resolution_note: string }) =>
    requestData<ReviewItem>(request.post(`/reviews/${id}/resolve`, payload)),

  escalateReview: (id: number, payload: { reason: string }) =>
    requestData<ReviewItem>(request.post(`/reviews/${id}/escalate`, payload)),

  // ISS-060: 领取复核任务（后端 /reviews/{id}/assign 为 POST 端点）
  assignReview: (id: number) =>
    requestData<ReviewItem>(request.post(`/reviews/${id}/assign`)),
}

import request, { requestData, requestPageData } from './request'
import { buildPageParams } from './business.shared'
import type { PageQuery } from '@/types/api'
import type { WarningItem, UserBindingInfo } from './userTypes'
import type { ConsultationGroupItem, ConsultationItem, UserManageItem } from './counselorTypes'

export type { WarningItem, UserBindingInfo } from './userTypes'
export type { ConsultationGroupItem, ConsultationItem, UserManageItem } from './counselorTypes'

export const counselorApi = {
  getCounselorWarnings: (query?: PageQuery & { only_unhandled?: boolean }) =>
    requestPageData<WarningItem>(request.get('/counselor/warnings', { params: { ...buildPageParams(query), only_unhandled: query?.only_unhandled } })),

  handleCounselorWarning: (warningId: number, action: 'handle' | 'ignore', note?: string) =>
    requestData<{ message: string }>(request.put(`/counselor/warnings/${warningId}/handle`, { action, note })),

  getCounselorUsers: (query?: PageQuery) => requestPageData<UserManageItem>(request.get('/counselor/users', { params: buildPageParams(query) })),

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
}

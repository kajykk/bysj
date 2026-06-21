import request, { requestData, requestPageData } from './request'
import { buildPageParams } from './business.shared'
import type { PageQuery } from '@/types/api'
import type { AssessmentType } from '@/types/contracts'
import type { AssessmentRecordItem, DataHistoryItem, WarningItem, WarningSettingData } from './userTypes'

export const userWarningsApi = {
  getUserWarnings: (query?: PageQuery & { is_read?: boolean }) =>
    requestPageData<WarningItem>(request.get('/user/warnings', { params: { ...buildPageParams(query), is_read: query?.is_read } })),

  markUserWarningRead: (warningId: number) => requestData<{ message: string }>(request.put(`/user/warnings/${warningId}/read`)),

  getUserAssessmentHistory: (query?: PageQuery & { type?: AssessmentType | 'structured' | 'text' | 'physiological'; start_date?: string; end_date?: string }) =>
    requestPageData<DataHistoryItem>(
      request.get('/user/data/history', { params: { ...buildPageParams(query), type: query?.type, start_date: query?.start_date, end_date: query?.end_date } })
    ),

  getDataHistory: (query?: PageQuery & { type?: string }) =>
    requestPageData<DataHistoryItem>(request.get('/user/data/history', { params: { ...buildPageParams(query), type: query?.type } })),

  getWarningSettings: () => requestData<WarningSettingData>(request.get('/user/warning-settings')),

  updateWarningSettings: (payload: Partial<WarningSettingData> & { notify_channels?: Record<string, boolean> }) => {
    const normalizedPayload = {
      ...payload,
      notify_channels: payload.notify_channels ?? undefined,
      quiet_hours_start: payload.quiet_hours_start || undefined,
      quiet_hours_end: payload.quiet_hours_end || undefined,
    }
    return requestData<{ message: string }>(request.put('/user/warning-settings', normalizedPayload))
  },

  markAllWarningsRead: () => requestData<{ message: string; count: number }>(request.put('/user/warnings/read-all')),
}

import request, { dedupedGet, requestData, requestPageData } from './request'
import { buildPageParams } from './business.shared'
import type { PageQuery } from '@/types/api'
import type { AssessmentType } from '@/types/contracts'
import type { DataHistoryItem, WarningItem, WarningSettingData } from './userTypes'

/**
 * 用户预警统计（GET /user/warnings/stats，P1-15 / F-03）。
 *
 * SQL 层聚合，口径同 getUserWarnings：分级按 current_level 原始数值
 * （3/2/1），已处理 = is_handled，未读 = is_read 为 false。
 */
export interface UserWarningStats {
  total: number
  high_risk: number
  medium_risk: number
  low_risk: number
  handled: number
  unread: number
}

/**
 * 用户评估历史统计（GET /user/data/history/stats，P1-15 / F-03）。
 *
 * SQL 层聚合，口径同 getUserAssessmentHistory：风险分档只统计有 0-100
 * 风险分的结构化记录（score >= 62 高 / >= 42 中 / >= 22 低）。
 */
export interface AssessmentHistoryStats {
  total: number
  structured: number
  text: number
  physiological: number
  high_risk: number
  medium_risk: number
  low_risk: number
}

export const userWarningsApi = {
  getUserWarnings: (query?: PageQuery & { is_read?: boolean }) =>
    requestPageData<WarningItem>(dedupedGet('/user/warnings', { params: { ...buildPageParams(query), is_read: query?.is_read } })),

  // P1-15 / F-03: 预警统计（SQL 层聚合）。原实现 page_size:200 拉全量到前端
  // filter，预警超 200 条时分子截断、分母不截断，统计结果是错的。
  getUserWarningStats: () =>
    requestData<UserWarningStats>(dedupedGet('/user/warnings/stats')),

  markUserWarningRead: (warningId: number) => requestData<{ message: string }>(request.put(`/user/warnings/${warningId}/read`)),

  getUserAssessmentHistory: (query?: PageQuery & { type?: AssessmentType | 'structured' | 'text' | 'physiological'; start_date?: string; end_date?: string }) =>
    requestPageData<DataHistoryItem>(
      dedupedGet('/user/data/history', { params: { ...buildPageParams(query), type: query?.type, start_date: query?.start_date, end_date: query?.end_date } })
    ),

  // P1-15 / F-03: 评估历史统计（SQL 层聚合）。原实现对三种类型各发一次
  // page_size:200 请求再合并 filter，超 200 条时分子截断、分母不截断，
  // 且一次页面打开最多传输 600 条完整记录（text 类型含用户正文）。
  getUserAssessmentHistoryStats: () =>
    requestData<AssessmentHistoryStats>(dedupedGet('/user/data/history/stats')),

  getDataHistory: (query?: PageQuery & { type?: string }) =>
    requestPageData<DataHistoryItem>(dedupedGet('/user/data/history', { params: { ...buildPageParams(query), type: query?.type } })),

  getWarningSettings: () => requestData<WarningSettingData>(dedupedGet('/user/warning-settings')),

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

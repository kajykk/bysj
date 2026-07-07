import request, { requestData, requestPageData } from './request'
import { buildPageParams } from './business.shared'
import type { PageQuery } from '@/types/api'
import type { UnifiedPageResult } from '@/types/contracts'

// ===== 告警历史 =====

export type AlertSeverity = 'P0' | 'P1' | 'P2'
export type AlertStatus = 'firing' | 'resolved'

export interface AlertHistoryItem {
  id: number
  rule: string
  severity: string
  status: string
  message: string
  fingerprint: string | null
  operator_id: number | null
  operator_role: string | null
  created_at: string | null
}

export interface AlertHistoryQuery extends PageQuery {
  severity?: AlertSeverity
  status?: AlertStatus
  start_time?: string
  end_time?: string
}

// ===== 告警归档 =====

export interface AlertArchiveItem {
  id: number
  original_id: number
  rule: string
  severity: string
  status: string
  message: string
  labels: Record<string, string>
  annotations: Record<string, string>
  fingerprint: string | null
  original_created_at: string | null
  archived_at: string | null
}

export interface AlertArchiveQuery extends PageQuery {
  rule?: string
  severity?: AlertSeverity
  status?: AlertStatus
  start_time?: string
  end_time?: string
}

// ===== 静默规则 =====

export interface SilenceItem {
  id: number
  name: string
  matcher: Record<string, string>
  starts_at: string | null
  ends_at: string | null
  created_by: number | null
  created_at: string | null
  comment: string | null
  is_active: boolean
}

export interface SilenceCreatePayload {
  name: string
  matcher: Record<string, string>
  starts_at: string
  ends_at: string
  comment?: string | null
}

export interface SilenceListQuery extends PageQuery {
  is_active?: boolean
}

// ===== API =====

export const alertsApi = {
  // 告警历史: GET /alerts/history
  listAlertHistory: (query?: AlertHistoryQuery) =>
    requestPageData<AlertHistoryItem>(
      request.get('/alerts/history', {
        params: {
          ...buildPageParams(query),
          severity: query?.severity,
          status: query?.status,
          start_time: query?.start_time,
          end_time: query?.end_time
        }
      })
    ),

  // 确认告警: POST /alerts/{id}/ack
  ackAlert: (id: number) =>
    requestData<{ alert_id: number; acknowledged: boolean }>(
      request.post(`/alerts/${id}/ack`)
    ),

  // 告警归档列表: GET /alerts/archive
  // 注: 后端无 POST /alerts/{id}/archive 端点, 归档由 Celery 定时任务自动完成,
  // 此处提供归档列表查询用于审计复盘
  listAlertArchive: (query?: AlertArchiveQuery) =>
    requestPageData<AlertArchiveItem>(
      request.get('/alerts/archive', {
        params: {
          ...buildPageParams(query),
          rule: query?.rule,
          severity: query?.severity,
          status: query?.status,
          start_time: query?.start_time,
          end_time: query?.end_time
        }
      })
    ),

  // 静默规则列表: GET /alerts/silences
  listSilences: (query?: SilenceListQuery) =>
    requestPageData<SilenceItem>(
      request.get('/alerts/silences', {
        params: {
          ...buildPageParams(query),
          is_active: query?.is_active
        }
      })
    ),

  // 当前生效的静默规则: GET /alerts/silences/active
  listActiveSilences: () =>
    requestData<{ items: SilenceItem[]; total: number }>(
      request.get('/alerts/silences/active')
    ),

  // 创建静默规则: POST /alerts/silences
  createSilence: (payload: SilenceCreatePayload) =>
    requestData<SilenceItem>(request.post('/alerts/silences', payload)),

  // ISS-073: 编辑静默规则: PUT /alerts/silences/{id}
  updateSilence: (id: number, payload: SilenceCreatePayload) =>
    requestData<SilenceItem>(request.put(`/alerts/silences/${id}`, payload)),

  // ISS-073: 启用已停用的静默规则: POST /alerts/silences/{id}/enable
  enableSilence: (id: number) =>
    requestData<SilenceItem>(request.post(`/alerts/silences/${id}/enable`)),

  // 删除静默规则: DELETE /alerts/silences/{id}
  deleteSilence: (id: number) =>
    requestData<{ id: number; is_active: boolean }>(
      request.delete(`/alerts/silences/${id}`)
    )
}

// 兼容分页结果归一化: listActiveSilences 返回 { items, total } 但非标准分页结构,
// 提供工具函数转换为 UnifiedPageResult 便于页面统一处理
// L-FE-17 修复：默认 page_size 改为固定值 20，原 raw.items.length 语义不直观且空列表时为 0
export function toPageResult<T>(raw: { items: T[]; total: number }, page = 1, page_size = 20): UnifiedPageResult<T> {
  return { items: raw.items, total: raw.total, page, page_size }
}

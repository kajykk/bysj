// frontend/src/api/observabilityApi.ts
import request from './request'

export interface ObservabilityEnvelope<T> {
  data: T
  instance_id: string
  cached: boolean
  generated_at: string
}

export interface ObservabilityTimeRange {
  start_time?: string
  end_time?: string
}

export interface ObservabilityTrendQuery extends ObservabilityTimeRange {
  bucket?: 'hour' | 'day'
  severity?: string
  status?: string
  group_by?: string
}

function get<T>(url: string, params?: Record<string, unknown>): Promise<ObservabilityEnvelope<T>> {
  return request.get<ObservabilityEnvelope<T>>(url, { params }).then((res) => res.data)
}

export const observabilityApi = {
  getHealth: (q?: ObservabilityTimeRange) => get<{ status: string; [k: string]: unknown }>('/alerts/observability/health', q as Record<string, unknown>),
  getTrend: (q?: ObservabilityTrendQuery) => get<{ points: unknown[]; [k: string]: unknown }>('/alerts/observability/trend', q as Record<string, unknown>),
  getResponseTime: (q?: ObservabilityTrendQuery) => get<{ avg_ms: number; [k: string]: unknown }>('/alerts/observability/response-time', q as Record<string, unknown>),
  getEscalation: (q?: ObservabilityTimeRange) => get<{ escalation_rate: number; [k: string]: unknown }>('/alerts/observability/escalation', q as Record<string, unknown>),
  getChannelStats: (q?: ObservabilityTimeRange) => get<{ channels: unknown[]; [k: string]: unknown }>('/alerts/observability/channel-stats', q as Record<string, unknown>),
  getSilenceHitRate: (q?: ObservabilityTimeRange) => get<{ hit_rate: number; [k: string]: unknown }>('/alerts/observability/silence-hit-rate', q as Record<string, unknown>),
  getAmSync: (q?: ObservabilityTimeRange) => get<{ last_sync: string; [k: string]: unknown }>('/alerts/observability/am-sync', q as Record<string, unknown>),
  getLockStats: (q?: ObservabilityTimeRange) => get<{ active_locks: number; [k: string]: unknown }>('/alerts/observability/lock-stats', q as Record<string, unknown>),
}

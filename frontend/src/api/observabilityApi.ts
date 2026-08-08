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
  // M-FIX-002: 与后端 bucket 枚举对齐 (observability/__init__.py 仅接受 5m/15m/1h/6h/1d)
  bucket?: '5m' | '15m' | '1h' | '6h' | '1d'
  severity?: string
  status?: string
  group_by?: string
}

function get<T>(url: string, params?: Record<string, unknown>): Promise<ObservabilityEnvelope<T>> {
  return request.get<ObservabilityEnvelope<T>>(url, { params }).then((res) => res.data)
}

export const observabilityApi = {
  getHealth: (q?: ObservabilityTimeRange) => get<{ endpoint: string; status: string; version: string; [k: string]: unknown }>('/alerts/observability/health', q as Record<string, unknown>),
  // H-AUDIT-01: 与后端 _compute_trend 对齐 (buckets/total/by_severity)
  getTrend: (q?: ObservabilityTrendQuery) => get<{ buckets: { timestamp: string; count: number; by_severity: Record<string, number>; by_status: Record<string, number> }[]; total: number; by_severity: Record<string, number>; [k: string]: unknown }>('/alerts/observability/trend', q as Record<string, unknown>),
  // H-AUDIT-01: 与后端 _compute_response_time 对齐 (response_time.mean)
  getResponseTime: (q?: ObservabilityTrendQuery) => get<{ total_fired: number; response_time: { mean: number; p50: number; p95: number; p99: number; max: number; min: number }; ack_rate: number; [k: string]: unknown }>('/alerts/observability/response-time', q as Record<string, unknown>),
  getEscalation: (q?: ObservabilityTimeRange) => get<{ total_fired: number; total_escalated: number; escalation_rate: number; by_level: Record<string, number>; by_severity: Record<string, number>; by_rule: unknown[]; [k: string]: unknown }>('/alerts/observability/escalation', q as Record<string, unknown>),
  getChannelStats: (q?: ObservabilityTimeRange) => get<{ channels: unknown[]; total: number; [k: string]: unknown }>('/alerts/observability/channel-stats', q as Record<string, unknown>),
  getSilenceHitRate: (q?: ObservabilityTimeRange) => get<{ total_fired: number; total_silenced: number; total_processed: number; hit_rate: number; by_matcher: Record<string, number>; by_severity: Record<string, number>; [k: string]: unknown }>('/alerts/observability/silence-hit-rate', q as Record<string, unknown>),
  // H-AUDIT-01: 与后端 _compute_am_sync 对齐 (success_rate)
  getAmSync: (q?: ObservabilityTimeRange) => get<{ total_success: number; total_failed: number; total: number; success_rate: number; avg_duration_ms: number; by_operation: Record<string, unknown>; recent_failures: unknown[]; [k: string]: unknown }>('/alerts/observability/am-sync', q as Record<string, unknown>),
  // H-AUDIT-01: 与后端 _compute_lock_stats 对齐 (memory.total)
  getLockStats: (q?: ObservabilityTimeRange) => get<{ memory: { acquired: number; skipped: number; fallback: number; errors: number; total: number; acquire_rate: number; fallback_rate: number; error_rate: number }; last_flush_at: string | null; recent_flushes: unknown[]; historical_recent: unknown[]; [k: string]: unknown }>('/alerts/observability/lock-stats', q as Record<string, unknown>),
}

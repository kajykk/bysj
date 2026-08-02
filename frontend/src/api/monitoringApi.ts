// frontend/src/api/monitoringApi.ts
import request, { requestData } from './request'

export interface MonitoringTimeRange { start_time?: string; end_time?: string }
export interface MonitoringSummary {
  inference_count_24h: number
  fallback_count_24h: number
  fallback_rate: number
  active_drift_alerts: number
  avg_latency_ms: number
  [k: string]: unknown
}
export interface ModelSuccessRatePoint {
  time_bucket: string
  total: number
  success: number
  fallback: number
  success_rate: number
}
export interface FallbackReason { reason: string; count: number; percentage: number }
export interface RequestDetailItem { id: number; [k: string]: unknown }
export interface RequestDetailsList { items: RequestDetailItem[]; total: number; [k: string]: unknown }

export const monitoringApi = {
  getDashboardSummary: () => requestData<MonitoringSummary>(request.get('/monitoring/dashboard-summary')),
  getModelSuccessRate: (q?: MonitoringTimeRange) => requestData<{ granularity: string; data: ModelSuccessRatePoint[] }>(request.get('/monitoring/model-success-rate', { params: q })),
  getFallbackStats: (q?: MonitoringTimeRange) => requestData<{ total: number; reasons: FallbackReason[] }>(request.get('/monitoring/fallback-stats', { params: q })),
  getDriftAlerts: (q?: MonitoringTimeRange) => requestData<{ total: number; alerts: RequestDetailItem[] }>(request.get('/monitoring/drift-alerts', { params: q })),
  getEngineSnapshot: () => requestData<{ cache_size?: number; [k: string]: unknown }>(request.get('/monitoring/engine-snapshot', { params: undefined })),
  getRequestDetailsList: (q?: { limit?: number; offset?: number } & MonitoringTimeRange) => requestData<RequestDetailsList>(request.get('/monitoring/request-details', { params: q })),
  getRequestDetail: (logId: number) => requestData<RequestDetailItem>(request.get(`/monitoring/request-details/${logId}`)),
}

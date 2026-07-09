// frontend/src/api/monitoringApi.ts
import request, { requestData } from './request'

export interface MonitoringTimeRange { start_time?: string; end_time?: string }
export interface MonitoringSummary { total_requests: number; success_rate?: number; [k: string]: unknown }
export interface RequestDetailItem { log_id: string; [k: string]: unknown }
export interface RequestDetailsList { items: RequestDetailItem[]; total: number; [k: string]: unknown }

export const monitoringApi = {
  getDashboardSummary: () => requestData<MonitoringSummary>(request.get('/monitoring/dashboard-summary')),
  getModelSuccessRate: (q?: MonitoringTimeRange) => requestData<{ rate: number; points?: unknown[]; [k: string]: unknown }>(request.get('/monitoring/model-success-rate', { params: q })),
  getFallbackStats: (q?: MonitoringTimeRange) => requestData<{ count: number; [k: string]: unknown }>(request.get('/monitoring/fallback-stats', { params: q })),
  getDriftAlerts: (q?: MonitoringTimeRange) => requestData<{ items: unknown[]; [k: string]: unknown }>(request.get('/monitoring/drift-alerts', { params: q })),
  getEngineSnapshot: () => requestData<{ engines: unknown[]; [k: string]: unknown }>(request.get('/monitoring/engine-snapshot', { params: undefined })),
  getRequestDetailsList: (q?: { limit?: number; offset?: number } & MonitoringTimeRange) => requestData<RequestDetailsList>(request.get('/monitoring/request-details', { params: q })),
  getRequestDetail: (logId: string) => requestData<RequestDetailItem>(request.get(`/monitoring/request-details/${logId}`)),
}

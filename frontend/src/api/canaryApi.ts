// frontend/src/api/canaryApi.ts
import request, { requestData } from './request'

export interface CanaryCreateRequest {
  version: string
  traffic_percent?: number
  thresholds?: Record<string, number> | null
}
export interface CanaryTrafficUpdateRequest { traffic_percent: number }
export interface CanaryRollbackRequest { reason: string }
export interface CanaryDeployment {
  id: number
  version: string
  traffic_percent: number
  status: string
  started_at: string | null
  created_at: string | null
}
export interface CanaryListResponse {
  total: number
  limit: number
  offset: number
  items: CanaryDeployment[]
}

export const canaryApi = {
  listCanaryDeployments: () => requestData<CanaryListResponse>(request.get('/canary/deployments')),
  getCanaryDeployment: (id: number) => requestData<CanaryDeployment>(request.get(`/canary/deployments/${id}`)),
  createCanaryDeployment: (payload: CanaryCreateRequest) => requestData<CanaryDeployment>(request.post('/canary/deployments', payload)),
  updateCanaryTraffic: (id: number, payload: CanaryTrafficUpdateRequest) => requestData<CanaryDeployment>(request.patch(`/canary/deployments/${id}/traffic`, payload)),
  pauseCanary: (id: number) => requestData<CanaryDeployment>(request.post(`/canary/deployments/${id}/pause`)),
  resumeCanary: (id: number) => requestData<CanaryDeployment>(request.post(`/canary/deployments/${id}/resume`)),
  rollbackCanary: (id: number, payload: CanaryRollbackRequest) => requestData<CanaryDeployment>(request.post(`/canary/deployments/${id}/rollback`, payload)),
  completeCanary: (id: number) => requestData<CanaryDeployment>(request.post(`/canary/deployments/${id}/complete`)),
  getCanaryTrafficPercentages: () => requestData<{ percentages: number[] }>(request.get('/canary/traffic-percentages')),
}

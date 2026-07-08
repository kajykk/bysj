import { PAGE_PERMISSIONS, OPERATION_PERMISSIONS } from './permissions'

export { PAGE_PERMISSIONS, OPERATION_PERMISSIONS }

export const ROUTE_PERMISSIONS = {
  userWarnings: [...PAGE_PERMISSIONS.userWarnings, ...OPERATION_PERMISSIONS.userWarnings],
  userAssessments: [...PAGE_PERMISSIONS.userAssessments, ...OPERATION_PERMISSIONS.userAssessments],
  counselorWarnings: [...PAGE_PERMISSIONS.counselorWarnings, ...OPERATION_PERMISSIONS.counselorWarnings],
  counselorConsultation: [...PAGE_PERMISSIONS.counselorUsers, ...OPERATION_PERMISSIONS.counselorUsers],
  counselorReviews: [...PAGE_PERMISSIONS.counselorReviews, ...OPERATION_PERMISSIONS.counselorReviews],
  adminOperationLogs: [...PAGE_PERMISSIONS.adminOperationLogs, ...OPERATION_PERMISSIONS.adminOperationLogs],
  adminAlerts: [...PAGE_PERMISSIONS.adminAlerts, ...OPERATION_PERMISSIONS.adminAlerts],
  adminSilences: [...PAGE_PERMISSIONS.adminSilences, ...OPERATION_PERMISSIONS.adminSilences],
  userReports: [...PAGE_PERMISSIONS.userReports],
  adminReports: [...PAGE_PERMISSIONS.adminReports],
  adminObservability: [...PAGE_PERMISSIONS.adminObservability],
  adminMonitoring: [...PAGE_PERMISSIONS.adminMonitoring],
  adminCanary: [...PAGE_PERMISSIONS.adminCanary]
} as const

import type { PermissionKey } from '@/types/permission'
import { PAGE_PERMISSIONS, OPERATION_PERMISSIONS } from './permissions'

export { PAGE_PERMISSIONS, OPERATION_PERMISSIONS }

export const ROUTE_PERMISSIONS = {
  userWarnings: [...PAGE_PERMISSIONS.userWarnings, ...OPERATION_PERMISSIONS.userWarnings],
  userAssessments: [...PAGE_PERMISSIONS.userAssessments, ...OPERATION_PERMISSIONS.userAssessments],
  counselorWarnings: [...PAGE_PERMISSIONS.counselorWarnings, ...OPERATION_PERMISSIONS.counselorWarnings],
  counselorConsultation: [...PAGE_PERMISSIONS.counselorUsers, ...OPERATION_PERMISSIONS.counselorUsers],
  adminOperationLogs: [...PAGE_PERMISSIONS.adminOperationLogs, ...OPERATION_PERMISSIONS.adminOperationLogs]
} as const

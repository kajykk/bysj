import type { PermissionKey } from '@/types/permission'

export const PAGE_PERMISSIONS = {
  userDashboard: [],
  userContent: ['user.content.read'],
  userIntervention: ['user.intervention.read'],
  userWarnings: ['user.warning.read'],
  userAssessments: ['user.assessment.read'],
  counselorDashboard: [],
  counselorWarnings: ['counselor.warning.handle'],
  counselorUsers: ['counselor.user.consultation.view'],
  counselorSettings: ['counselor.settings.manage'],
  adminDashboard: [],
  adminTemplates: ['admin.template.manage'],
  adminSettings: ['admin.settings.manage'],
  adminOperationLogs: ['admin.operation_log.view']
} as const satisfies Record<string, readonly PermissionKey[]>

export const OPERATION_PERMISSIONS = {
  userWarnings: ['user.warning.track'],
  userAssessments: [],
  counselorWarnings: ['counselor.warning.ignore', 'counselor.warning.batch'],
  counselorUsers: [],
  counselorSettings: [],
  adminTemplates: [],
  adminSettings: [],
  adminOperationLogs: ['admin.operation_log.filter', 'admin.operation_log.audit']
} as const satisfies Record<string, readonly PermissionKey[]>

export const ROLE_PERMISSIONS: Record<string, readonly PermissionKey[]> = {
  user: [...PAGE_PERMISSIONS.userDashboard, ...PAGE_PERMISSIONS.userContent, ...PAGE_PERMISSIONS.userIntervention, ...PAGE_PERMISSIONS.userWarnings, ...PAGE_PERMISSIONS.userAssessments, ...OPERATION_PERMISSIONS.userWarnings, ...OPERATION_PERMISSIONS.userAssessments, 'user.predict.use', 'user.export.risk'],
  counselor: [...PAGE_PERMISSIONS.counselorDashboard, ...PAGE_PERMISSIONS.counselorWarnings, ...PAGE_PERMISSIONS.counselorUsers, ...PAGE_PERMISSIONS.counselorSettings, ...OPERATION_PERMISSIONS.counselorWarnings, ...OPERATION_PERMISSIONS.counselorUsers, ...OPERATION_PERMISSIONS.counselorSettings, 'counselor.predict.use'],
  admin: [...PAGE_PERMISSIONS.adminDashboard, ...PAGE_PERMISSIONS.adminTemplates, ...PAGE_PERMISSIONS.adminSettings, ...PAGE_PERMISSIONS.adminOperationLogs, ...OPERATION_PERMISSIONS.adminTemplates, ...OPERATION_PERMISSIONS.adminSettings, ...OPERATION_PERMISSIONS.adminOperationLogs, 'admin.predict.audit']
}

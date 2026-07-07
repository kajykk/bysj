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
  counselorReviews: ['review.view'],
  counselorSettings: ['counselor.settings.manage'],
  adminDashboard: [],
  adminTemplates: ['admin.template.manage'],
  adminSettings: ['admin.settings.manage'],
  adminOperationLogs: ['admin.operation_log.view'],
  adminAlerts: ['admin.alerts.view'],
  adminSilences: ['admin.silences.manage']
} as const satisfies Record<string, readonly PermissionKey[]>

export const OPERATION_PERMISSIONS = {
  userWarnings: ['user.warning.track'],
  userAssessments: [],
  counselorWarnings: ['counselor.warning.ignore', 'counselor.warning.batch'],
  counselorUsers: [],
  counselorReviews: ['review.handle'],
  counselorSettings: [],
  adminTemplates: [],
  adminSettings: [],
  adminOperationLogs: ['admin.operation_log.filter', 'admin.operation_log.audit'],
  adminAlerts: [],
  adminSilences: []
} as const satisfies Record<string, readonly PermissionKey[]>

export const ROLE_PERMISSIONS: Record<string, readonly PermissionKey[]> = {
  user: [...PAGE_PERMISSIONS.userDashboard, ...PAGE_PERMISSIONS.userContent, ...PAGE_PERMISSIONS.userIntervention, ...PAGE_PERMISSIONS.userWarnings, ...PAGE_PERMISSIONS.userAssessments, ...OPERATION_PERMISSIONS.userWarnings, ...OPERATION_PERMISSIONS.userAssessments, 'user.predict.use', 'user.export.risk'],
  counselor: [...PAGE_PERMISSIONS.counselorDashboard, ...PAGE_PERMISSIONS.counselorWarnings, ...PAGE_PERMISSIONS.counselorUsers, ...PAGE_PERMISSIONS.counselorReviews, ...PAGE_PERMISSIONS.counselorSettings, ...OPERATION_PERMISSIONS.counselorWarnings, ...OPERATION_PERMISSIONS.counselorUsers, ...OPERATION_PERMISSIONS.counselorReviews, ...OPERATION_PERMISSIONS.counselorSettings, 'counselor.predict.use'],
  admin: [...PAGE_PERMISSIONS.adminDashboard, ...PAGE_PERMISSIONS.adminTemplates, ...PAGE_PERMISSIONS.adminSettings, ...PAGE_PERMISSIONS.adminOperationLogs, ...PAGE_PERMISSIONS.adminAlerts, ...PAGE_PERMISSIONS.adminSilences, ...PAGE_PERMISSIONS.counselorReviews, ...OPERATION_PERMISSIONS.adminTemplates, ...OPERATION_PERMISSIONS.adminSettings, ...OPERATION_PERMISSIONS.adminOperationLogs, ...OPERATION_PERMISSIONS.adminAlerts, ...OPERATION_PERMISSIONS.adminSilences, ...OPERATION_PERMISSIONS.counselorReviews, 'admin.predict.audit']
}

/**
 * 判断指定角色是否拥有某项权限。
 *
 * 此函数从 `@/types/permission` 迁移至 `@/config/permissions`：
 * 原实现中 `types/permission.ts` 通过 `import { ROLE_PERMISSIONS } from '@/config/permissions'`
 * 引入运行时数据，而 `permissions.ts` 通过 `import type { PermissionKey }` 引入类型，
 * 形成 type-only 循环依赖（madge 静态分析误报）。将函数下沉到数据所在模块后，
 * `types/permission.ts` 不再持有任何 import，循环被彻底消除。
 */
export const hasPermission = (role: string, permission: PermissionKey): boolean => {
  return (ROLE_PERMISSIONS[role] || []).includes(permission)
}

import { ROLE_PERMISSIONS } from '@/config/permissions'

export type PermissionKey =
  | 'user.warning.read'
  | 'user.warning.track'
  | 'user.assessment.read'
  | 'user.upload.manage'
  | 'user.export.risk'
  | 'user.predict.use'
  | 'counselor.warning.handle'
  | 'counselor.warning.ignore'
  | 'counselor.warning.batch'
  | 'counselor.user.consultation.view'
  | 'counselor.predict.use'
  | 'admin.operation_log.view'
  | 'admin.operation_log.filter'
  | 'admin.operation_log.audit'
  | 'admin.dashboard.view'
  | 'admin.settings.manage'
  | 'admin.template.manage'
  | 'admin.predict.audit'
  | 'user.dashboard.view'
  | 'user.content.read'
  | 'user.intervention.read'
  | 'user.settings.manage'
  | 'counselor.dashboard.view'
  | 'counselor.settings.manage'

export const hasPermission = (role: string, permission: PermissionKey): boolean => {
  return (ROLE_PERMISSIONS[role] || []).includes(permission)
}

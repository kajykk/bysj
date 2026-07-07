// 注意：hasPermission 已迁移至 @/config/permissions，以消除本文件与 config/permissions.ts 之间的
// type-only 循环依赖（原实现：本文件 import { ROLE_PERMISSIONS } from '@/config/permissions'，
// permissions.ts import type { PermissionKey } from '@/types/permission'）。
// 现在本文件仅导出类型定义，不持有任何 import，循环被彻底消除。

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
  | 'review.view'
  | 'review.handle'
  | 'admin.operation_log.view'
  | 'admin.operation_log.filter'
  | 'admin.operation_log.audit'
  | 'admin.alerts.view'
  | 'admin.silences.manage'
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

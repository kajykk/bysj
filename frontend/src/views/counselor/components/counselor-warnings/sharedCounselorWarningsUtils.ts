/**
 * CounselorWarnings 共享工具：类型、纯函数。
 * 从原 CounselorWarningsPage.vue 提取，保持行为一致。
 */
import { isWarningHandled } from '@/utils/warning'
import type { WarningItem } from '@/api/userTypes'

/** 行内动作类型：handle / ignore / escalate（ISS-058 扩展 escalate） */
export type RowAction = 'handle' | 'ignore' | 'escalate'

/** 行动作禁用判断所需上下文 */
export interface RowActionContext {
  canHandle: boolean
  canIgnore: boolean
  canEscalate: boolean
  batchOperating: boolean
  isActionPending: (id: number) => boolean
}

/** 预警是否已处理（handle / ignore / escalate 均视为已处理） */
export const isHandled = (row: WarningItem): boolean => isWarningHandled(row)

/** 获取行动作禁用原因（空串表示可执行） */
export const getRowDisabledReason = (
  row: WarningItem,
  action: RowAction,
  ctx: RowActionContext,
  t: (key: string) => string
): string => {
  if (action === 'handle' && !ctx.canHandle) return t('counselorWarnings.disabledNoHandlePermission')
  if (action === 'ignore' && !ctx.canIgnore) return t('counselorWarnings.disabledNoIgnorePermission')
  // ISS-058: 升级权限校验
  if (action === 'escalate' && !ctx.canEscalate) return t('counselorWarnings.disabledNoEscalatePermission')
  if (isHandled(row)) return t('counselorWarnings.disabledAlreadyHandled')
  if (ctx.isActionPending(row.id)) return t('counselorWarnings.disabledProcessing')
  if (ctx.batchOperating) return t('counselorWarnings.disabledBatchProcessing')
  return ''
}

/** 行动作是否禁用 */
export const isRowActionDisabled = (
  row: WarningItem,
  action: RowAction,
  ctx: RowActionContext,
  t: (key: string) => string
): boolean => !!getRowDisabledReason(row, action, ctx, t)

/** 行是否可选中（未处理且无进行中动作） */
export const isRowSelectable = (row: WarningItem, isActionPending: (id: number) => boolean): boolean =>
  !isHandled(row) && !isActionPending(row.id)

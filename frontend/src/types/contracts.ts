export const WARNING_STATUS = ['pending', 'handled', 'ignored'] as const
export type WarningStatus = (typeof WARNING_STATUS)[number]

export const RISK_LEVEL = ['low', 'medium', 'high'] as const
export type RiskLevel = (typeof RISK_LEVEL)[number]

export const USER_STATUS = ['active', 'inactive', 'disabled'] as const
export type UserStatus = (typeof USER_STATUS)[number]

export const ASSESSMENT_TYPE = ['structured', 'text', 'physiological'] as const
export type AssessmentType = (typeof ASSESSMENT_TYPE)[number]

export const ACTION_TYPE = ['login', 'logout', 'warning_handle', 'warning_ignore', 'warning_read', 'user_update', 'role_update', 'create_bind_code', 'refresh_bind_code', 'bind_counselor', 'unbind_counselor', 'add_group_member'] as const
export type ActionType = (typeof ACTION_TYPE)[number]

export const BINDING_STATUS = ['placeholder', 'active', 'inactive'] as const
export type BindingStatus = (typeof BINDING_STATUS)[number]

export interface UnifiedPageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export function normalizePageResult<T>(raw: unknown): UnifiedPageResult<T> {
  const data = (raw ?? {}) as Record<string, unknown>
  if (!Array.isArray(data.items)) throw new Error('分页契约错误: 缺少 items')
  if (typeof data.total !== 'number') throw new Error('分页契约错误: 缺少 total')
  if (typeof data.page !== 'number') throw new Error('分页契约错误: 缺少 page')
  if (typeof data.page_size !== 'number') throw new Error('分页契约错误: 缺少 page_size')

  return {
    items: data.items as T[],
    total: data.total,
    page: data.page,
    page_size: data.page_size
  }
}

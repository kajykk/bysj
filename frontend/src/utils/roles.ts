/**
 * P2-37：前端角色判定的唯一来源（SSOT）。
 *
 * 后端 SSOT 是 `app/core/contracts.py` 的 `USER_ROLE_*`；前端此前把
 * `'admin' | 'super_admin'` 这类字面量散落在 14 个文件（15 个行为判定），
 * 与后端常量无任何关联 —— 改一个角色名要碰十几个文件（根因②）。
 *
 * 本模块只收编**行为判定**，不碰：类型声明（`types/auth.ts` 的联合类型）、
 * 路由 path、`meta.role` 数组（守卫消费端已用 helper）、模板表单值、
 * `data-role` CSS、storage key。详见 `docs/P2_10_ROUND10_AUDIT.md` 豁免表。
 */
export const USER_ROLE_USER = 'user' as const
export const USER_ROLE_COUNSELOR = 'counselor' as const
export const USER_ROLE_ADMIN = 'admin' as const
export const USER_ROLE_SUPER_ADMIN = 'super_admin' as const

export type UserRole =
  | typeof USER_ROLE_USER
  | typeof USER_ROLE_COUNSELOR
  | typeof USER_ROLE_ADMIN
  | typeof USER_ROLE_SUPER_ADMIN

const KNOWN_ROLES: readonly string[] = [
  USER_ROLE_USER,
  USER_ROLE_COUNSELOR,
  USER_ROLE_ADMIN,
  USER_ROLE_SUPER_ADMIN,
]

/** 白名单校验：未知/空角色直接 false（App.vue 启动校验用）。 */
export function isKnownRole(role: unknown): role is UserRole {
  return typeof role === 'string' && KNOWN_ROLES.includes(role)
}

export function isUserRole(role: unknown): boolean {
  return role === USER_ROLE_USER
}

export function isStaffRole(role: unknown): boolean {
  return role === USER_ROLE_ADMIN || role === USER_ROLE_COUNSELOR
}

export function isAdminRole(role: unknown): boolean {
  return role === USER_ROLE_ADMIN || role === USER_ROLE_SUPER_ADMIN
}

export function isCounselorRole(role: unknown): boolean {
  return role === USER_ROLE_COUNSELOR
}

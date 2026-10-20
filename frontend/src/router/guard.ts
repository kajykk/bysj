import { hasPermission } from '@/config/permissions'
import type { PermissionKey } from '@/types/permission'
import { isAdminRole, isCounselorRole, isUserRole } from '@/utils/roles'

export interface GuardAuthState {
  isLoggedIn: boolean
  role: string
  /**
   * M26 修复（ROUND_23）：`role` 是否来自**已验证来源**。
   *
   * 未验证 = role 取自 localStorage 占位值（DevTools 可篡改），
   * 不能单独支撑权限决策；已验证 = role 与后端签发的 access_token
   * claims 一致（见 utils/authStorage 的 parseJwtRole）。
   * 缺省 false（fail-closed）：调用方不传即视为不可信。
   */
  roleVerified?: boolean
}

export interface GuardRouteMeta {
  // SEC-FIX (H5): 支持多角色路由（如 /user/model-training 允许 user 与 admin 访问），
  // 数组语义为“任一角色匹配即可”
  role?: string | string[]
  permissions?: PermissionKey[]
}

export const resolveRoleHome = (role: string): string => {
  // 平台管理员 (super_admin) 复用管理端首页
  if (isAdminRole(role)) return '/admin/dashboard'
  if (isCounselorRole(role)) return '/counselor/dashboard'
  if (isUserRole(role)) return '/user/dashboard'
  // L-FE-6 修复：未知角色不默认跳转用户首页，返回 /403 拒绝访问
  return '/403'
}

/**
 * M26 修复（ROUND_23）：该路由是否属于管理端（需已验证角色才能放行）。
 *
 * 判定两条：路径前缀 `/admin`，或 meta.role 命中 admin 类角色
 * （`isAdminRole` 含 super_admin）。二者取或——管理端路由既有按前缀
 * 也有按 meta 声明的写法，任一命中都要按管理端口径约束。
 */
const isAdminArea = (toPath: string, meta: GuardRouteMeta): boolean => {
  if (toPath.startsWith('/admin')) return true
  const roles = meta.role ? (Array.isArray(meta.role) ? meta.role : [meta.role]) : []
  // 只有当 meta.role **全部**是 admin 类时才按管理端口径约束。
  // 用 every 而非 some：`/user/model-training` 这类多角色路由
  // （['user','admin','super_admin']）位于用户区，若按 some 判定会把
  // 正常 admin 用户挡在门外——那是误伤，不是防护。
  return roles.length > 0 && roles.every((role) => isAdminRole(role))
}

export const resolveGuardResult = (toPath: string, meta: GuardRouteMeta, auth: GuardAuthState): true | string => {
  // M26 修复（ROUND_23）：未验证角色一律按「凭证待验证」处理——
  // 不放行管理端，也不按占位 role 做跳转决策（否则篡改 localStorage 的
  // super_admin 会被直接送进 /admin/dashboard，后台结构即暴露）。
  const roleVerified = auth.roleVerified === true

  // Public auth pages stay accessible to anonymous users, but logged-in users
  // should be routed to the correct dashboard to avoid landing on redundant screens.
  if (toPath === '/login' || toPath === '/reset-password') {
    if (!auth.isLoggedIn || !roleVerified) return true
    return resolveRoleHome(auth.role)
  }

  if (!auth.isLoggedIn) return '/login'

  if (!auth.role) return '/login'

  // 管理端：占位 role 不能单独支撑放行，回到登录页走一次真实凭证校验。
  if (isAdminArea(toPath, meta) && !roleVerified) return '/login'

  // Route-level role metadata acts as a coarse guard; permission metadata is the
  // finer-grained check used for pages that expose sensitive operations.
  // FM-05 修复：角色不匹配时重定向到 /forbidden 而非首页，让用户明确知道访问被拒绝，
  // 而非困惑地被跳转到首页。与下方权限检查的行为保持一致。
  // SEC-FIX (H5)：meta.role 支持数组，任一角色命中即放行
  if (meta.role) {
    const roles = Array.isArray(meta.role) ? meta.role : [meta.role]
    if (!roles.includes(auth.role)) {
      return '/forbidden'
    }
  }

  const routePermissions = meta.permissions || []
  if (routePermissions.length > 0) {
    const allowed = routePermissions.every((permission) => hasPermission(auth.role, permission))
    if (!allowed) return '/forbidden'
  }

  return true
}

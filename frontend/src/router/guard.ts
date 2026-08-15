import { hasPermission } from '@/config/permissions'
import type { PermissionKey } from '@/types/permission'

export interface GuardAuthState {
  isLoggedIn: boolean
  role: string
}

export interface GuardRouteMeta {
  // SEC-FIX (H5): 支持多角色路由（如 /user/model-training 允许 user 与 admin 访问），
  // 数组语义为“任一角色匹配即可”
  role?: string | string[]
  permissions?: PermissionKey[]
}

export const resolveRoleHome = (role: string): string => {
  // 平台管理员 (super_admin) 复用管理端首页
  if (role === 'admin' || role === 'super_admin') return '/admin/dashboard'
  if (role === 'counselor') return '/counselor/dashboard'
  if (role === 'user') return '/user/dashboard'
  // L-FE-6 修复：未知角色不默认跳转用户首页，返回 /403 拒绝访问
  return '/403'
}

export const resolveGuardResult = (toPath: string, meta: GuardRouteMeta, auth: GuardAuthState): true | string => {
  // Public auth pages stay accessible to anonymous users, but logged-in users
  // should be routed to the correct dashboard to avoid landing on redundant screens.
  if (toPath === '/login' || toPath === '/reset-password') {
    if (!auth.isLoggedIn) return true
    return resolveRoleHome(auth.role)
  }

  if (!auth.isLoggedIn) return '/login'

  if (!auth.role) return '/login'

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

import { hasPermission, type PermissionKey } from '@/types/permission'

export interface GuardAuthState {
  isLoggedIn: boolean
  role: string
}

export interface GuardRouteMeta {
  role?: string
  permissions?: PermissionKey[]
}

export const resolveRoleHome = (role: string): string => {
  if (role === 'admin') return '/admin/dashboard'
  if (role === 'counselor') return '/counselor/dashboard'
  return '/user/dashboard'
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
  if (meta.role && meta.role !== auth.role) {
    return resolveRoleHome(auth.role)
  }

  const routePermissions = meta.permissions || []
  if (routePermissions.length > 0) {
    const allowed = routePermissions.every((permission) => hasPermission(auth.role, permission))
    if (!allowed) return '/forbidden'
  }

  return true
}

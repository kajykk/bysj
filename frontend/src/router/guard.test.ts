import { describe, expect, it } from 'vitest'
import { resolveGuardResult, resolveRoleHome } from './guard'
import { ROUTE_PERMISSIONS } from '@/config/routeAccess'

describe('resolveRoleHome', () => {
  it('returns admin home for admin role', () => {
    expect(resolveRoleHome('admin')).toBe('/admin/dashboard')
  })

  it('returns counselor home for counselor role', () => {
    expect(resolveRoleHome('counselor')).toBe('/counselor/dashboard')
  })

  it('returns /403 for unknown roles', () => {
    // L-FE-6 修复：未知角色不默认跳转用户首页，返回 /403 拒绝访问
    expect(resolveRoleHome('guest')).toBe('/403')
  })
})

describe('resolveGuardResult', () => {
  it('allows anonymous access to login and reset password', () => {
    expect(resolveGuardResult('/login', {}, { isLoggedIn: false, role: '' })).toBe(true)
    expect(resolveGuardResult('/reset-password', {}, { isLoggedIn: false, role: '' })).toBe(true)
  })

  it('redirects logged-in users away from login page', () => {
    expect(resolveGuardResult('/login', {}, { isLoggedIn: true, role: 'user' })).toBe('/user/dashboard')
  })

  it('redirects unauthenticated users to login', () => {
    expect(resolveGuardResult('/user/dashboard', { role: 'user' }, { isLoggedIn: false, role: '' })).toBe('/login')
  })

  it('redirects mismatched roles to forbidden page', () => {
    expect(resolveGuardResult('/admin/dashboard', { role: 'admin' }, { isLoggedIn: true, role: 'user' })).toBe('/forbidden')
  })

  it('allows valid authorized access', () => {
    expect(
      resolveGuardResult(
        '/user/warnings',
        { role: 'user', permissions: [...ROUTE_PERMISSIONS.userWarnings] },
        { isLoggedIn: true, role: 'user' }
      )
    ).toBe(true)
  })
})

import { describe, expect, it } from 'vitest'
import { resolveGuardResult, resolveRoleHome } from './guard'
import { ROUTE_PERMISSIONS } from '@/config/routeAccess'

describe('resolveRoleHome', () => {
  it('returns admin home for admin role', () => {
    expect(resolveRoleHome('admin')).toBe('/admin/dashboard')
  })

  it('returns admin home for super_admin role', () => {
    expect(resolveRoleHome('super_admin')).toBe('/admin/dashboard')
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
    // M26 修复（ROUND_23）：roleVerified 表示角色来自已验证来源（token claims
    // 与内存角色一致）。已登录且已验证才按角色跳转。
    expect(
      resolveGuardResult('/login', {}, { isLoggedIn: true, role: 'user', roleVerified: true })
    ).toBe('/user/dashboard')
  })

  it('redirects unauthenticated users to login', () => {
    expect(resolveGuardResult('/user/dashboard', { role: 'user' }, { isLoggedIn: false, role: '' })).toBe('/login')
  })

  it('redirects mismatched roles to forbidden page', () => {
    expect(
      resolveGuardResult(
        '/admin/dashboard',
        { role: 'admin' },
        { isLoggedIn: true, role: 'user', roleVerified: true }
      )
    ).toBe('/forbidden')
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

  // ===== M26 修复（ROUND_23）：角色必须来自已验证来源，localStorage 占位值不能单独放行管理端 =====

  it('篡改 localStorage 为 super_admin 且无有效凭证 ⇒ 不放行 /admin/*', () => {
    // 场景：DevTools 改 localStorage.user.role='super_admin' 并刷新。
    // 内存角色确实是 super_admin，但 token claims 对不上 ⇒ roleVerified=false。
    expect(
      resolveGuardResult(
        '/admin/dashboard',
        { role: 'admin' },
        { isLoggedIn: true, role: 'super_admin', roleVerified: false }
      )
    ).toBe('/login')
    // 连 super_admin 自己的 meta 也不放行
    expect(
      resolveGuardResult(
        '/admin/users',
        { role: ['admin', 'super_admin'] },
        { isLoggedIn: true, role: 'super_admin', roleVerified: false }
      )
    ).toBe('/login')
  })

  it('未验证角色时不按占位 role 做跳转决策（/login 停在当前页）', () => {
    expect(
      resolveGuardResult('/login', {}, { isLoggedIn: true, role: 'super_admin', roleVerified: false })
    ).toBe(true)
    expect(
      resolveGuardResult(
        '/reset-password',
        {},
        { isLoggedIn: true, role: 'admin', roleVerified: false }
      )
    ).toBe(true)
  })

  it('不传 roleVerified 时按未验证处理（fail-closed，调用方漏传也不放行）', () => {
    expect(
      resolveGuardResult('/admin/dashboard', { role: 'admin' }, { isLoggedIn: true, role: 'admin' })
    ).toBe('/login')
  })

  it('已验证角色放行管理端（正常管理员链路不受影响）', () => {
    expect(
      resolveGuardResult(
        '/admin/dashboard',
        { role: 'admin' },
        { isLoggedIn: true, role: 'admin', roleVerified: true }
      )
    ).toBe(true)
    expect(
      resolveGuardResult(
        '/admin/dashboard',
        { role: ['admin', 'super_admin'] },
        { isLoggedIn: true, role: 'super_admin', roleVerified: true }
      )
    ).toBe(true)
  })

  it('多角色用户区路由不按管理端口径约束（防误伤正常 admin）', () => {
    // /user/model-training 允许 user/admin/super_admin：
    // 未验证的 admin 应走"角色不匹配"路径而非被管理端规则拦到 /login
    const meta = { role: ['user', 'admin', 'super_admin'] }
    expect(
      resolveGuardResult(
        '/user/model-training',
        meta,
        { isLoggedIn: true, role: 'admin', roleVerified: false }
      )
    ).toBe(true)
  })

  it('allows array roles when any matches (SEC-FIX H5)', () => {
    // /user/model-training: user / admin / super_admin 均可访问
    expect(
      resolveGuardResult('/user/model-training', { role: ['user', 'admin', 'super_admin'] }, { isLoggedIn: true, role: 'user' })
    ).toBe(true)
    expect(
      resolveGuardResult('/user/model-training', { role: ['user', 'admin', 'super_admin'] }, { isLoggedIn: true, role: 'admin' })
    ).toBe(true)
    expect(
      resolveGuardResult('/user/model-training', { role: ['user', 'admin', 'super_admin'] }, { isLoggedIn: true, role: 'super_admin' })
    ).toBe(true)
    // counselor 不在白名单 -> forbidden
    expect(
      resolveGuardResult('/user/model-training', { role: ['user', 'admin', 'super_admin'] }, { isLoggedIn: true, role: 'counselor' })
    ).toBe('/forbidden')
  })
})

import { describe, it, expect, vi } from 'vitest'

/**
 * AUDIT-2026-10-01：侧边栏分组回归测试。
 *
 * 背景：`groupedMenus` 用正则把菜单项分进 daily / review / ops / settings 四组，
 * **未被任何正则命中的 item 不会出现在侧边栏**。
 *
 * 这个坑实际踩了三次：
 *   1. `reviewItems` 原为 `/assessment|report/`，于是 `/counselor/reviews` 被隐藏；
 *   2. `/admin/templates` 不匹配任何正则；
 *   3. `/user/model-training` 不匹配任何正则。
 * （`/admin/model-kill-switch` 是准备新增时发现的第四次。）
 *
 * 因此修复方式不是继续往正则里补词，而是加了「兜底分组」：未命中任何正则的项
 * 也会渲染。下面这些清单即「所有菜单项都必须可见」的契约。
 */

const USER_PATHS = [
  '/user/dashboard',
  '/user/risk',
  '/user/model-training',
  '/user/intervention',
  '/user/content',
  '/user/warnings',
  '/user/assessments',
  '/user/settings',
  '/user/reports',
]

const COUNSELOR_PATHS = [
  '/counselor/dashboard',
  '/counselor/warnings',
  '/counselor/users',
  '/counselor/reviews',
  '/counselor/settings',
]

const ADMIN_PATHS = [
  '/admin/dashboard',
  '/admin/templates',
  '/admin/settings',
  '/admin/operation-logs',
  // AUDIT-2026-10-01 (P2)：合规审计日志页
  '/admin/audit-logs',
  '/admin/alerts',
  '/admin/silences',
  '/admin/crisis-events',
  '/counselor/reviews',
  '/admin/reports',
  '/admin/observability',
  '/admin/monitoring',
  '/admin/canary',
  '/admin/model-kill-switch',
]

const { roleRef } = vi.hoisted(() => ({ roleRef: { value: 'counselor' } }))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ role: roleRef.value }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/counselor/reviews' }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import { useLayoutMenu } from './useLayoutMenu'

/** 以指定角色求值一次侧边栏，返回所有可见菜单项的 path。 */
const visiblePaths = (role: string): string[] => {
  roleRef.value = role
  const { groupedMenus } = useLayoutMenu()
  return groupedMenus.value.flatMap((section) => section.items.map((item) => item.path))
}

describe('useLayoutMenu 分组', () => {
  it('counselor 侧边栏包含复核任务页（回归：原正则漏 review 导致其被隐藏）', () => {
    expect(visiblePaths('counselor')).toContain('/counselor/reviews')
  })

  it('admin 侧边栏包含复核任务页（「指定分配」入口）', () => {
    const paths = visiblePaths('admin')
    expect(paths).toContain('/counselor/reviews')
    expect(paths).toContain('/admin/dashboard')
  })

  it('super_admin 与 admin 共用同一套平台菜单', () => {
    const adminPaths = visiblePaths('admin')
    expect(visiblePaths('super_admin')).toEqual(adminPaths)
  })

  it('admin 侧边栏包含模型暂停开关（P1-7：事故止血入口必须可达）', () => {
    expect(visiblePaths('admin')).toContain('/admin/model-kill-switch')
  })

  it('历史漏项：模板管理与模型训练也必须可见', () => {
    expect(visiblePaths('admin')).toContain('/admin/templates')
    expect(visiblePaths('user')).toContain('/user/model-training')
  })

  it('没有任何菜单项被分组漏掉（兜底分组回归：数量与清单双向一致）', () => {
    for (const [role, expected] of [
      ['user', USER_PATHS],
      ['counselor', COUNSELOR_PATHS],
      ['admin', ADMIN_PATHS],
      ['super_admin', ADMIN_PATHS],
    ] as const) {
      const shown = visiblePaths(role)
      // 数量相等同时排除「丢失」与「重复渲染」
      expect(shown.length, `${role} 可见项数`).toBe(expected.length)
      for (const path of expected) {
        expect(shown, `${role} 缺少 ${path}`).toContain(path)
      }
    }
  })
})

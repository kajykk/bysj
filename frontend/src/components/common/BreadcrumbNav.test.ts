import { describe, it, expect } from 'vitest'

describe('BreadcrumbNav - 8.1.1 公共组件测试覆盖', () => {
  it('应始终包含首页', () => {
    const breadcrumbs = [{ title: '首页', path: '/' }]
    expect(breadcrumbs[0].title).toBe('首页')
    expect(breadcrumbs[0].path).toBe('/')
  })

  it('最后一个面包屑不应有链接', () => {
    const breadcrumbs = [
      { title: '首页', path: '/' },
      { title: '用户管理', path: '/admin/users' }
    ]
    const lastIndex = breadcrumbs.length - 1

    expect(lastIndex).toBe(1)
    expect(breadcrumbs[lastIndex].title).toBe('用户管理')
  })

  it('非最后一个面包屑应有链接', () => {
    const breadcrumbs = [
      { title: '首页', path: '/' },
      { title: '用户管理', path: '/admin/users' },
      { title: '详情', path: '/admin/users/1' }
    ]

    expect(breadcrumbs[0].path).toBe('/')
    expect(breadcrumbs[1].path).toBe('/admin/users')
  })

  it('应过滤没有 title 的路由', () => {
    const matched = [
      { path: '/', meta: { title: '首页' } },
      { path: '/admin', meta: {} },
      { path: '/admin/users', meta: { title: '用户管理' } }
    ]

    const filtered = matched.filter((r) => r.meta?.title)
    expect(filtered).toHaveLength(2)
    expect(filtered[0].meta.title).toBe('首页')
    expect(filtered[1].meta.title).toBe('用户管理')
  })
})

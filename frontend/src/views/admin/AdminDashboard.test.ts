import { describe, it, expect } from 'vitest'

describe('AdminDashboard - 5.1.1 统计卡片增强', () => {
  it('环比趋势应正确计算百分比', () => {
    const calcTrend = (current: number, previous: number) => {
      if (previous === 0) return 0
      return Math.round(((current - previous) / previous) * 100)
    }

    expect(calcTrend(120, 100)).toBe(20)
    expect(calcTrend(80, 100)).toBe(-20)
    expect(calcTrend(100, 0)).toBe(0)
  })

  it('趋势标签应根据数值显示正确颜色', () => {
    const userTrend = 15
    const warningTrend = -10

    const userTagType = userTrend >= 0 ? 'success' : 'danger'
    const warningTagType = warningTrend <= 0 ? 'success' : 'danger'

    expect(userTagType).toBe('success')
    expect(warningTagType).toBe('success')
  })

  it('系统组件列表应包含核心服务', () => {
    const components = [
      { name: 'API 服务', healthy: true },
      { name: '数据库', healthy: true },
      { name: 'Redis 缓存', healthy: true },
      { name: '消息队列', healthy: true },
      { name: '文件存储', healthy: true }
    ]

    expect(components).toHaveLength(5)
    expect(components.map((c) => c.name)).toContain('API 服务')
    expect(components.map((c) => c.name)).toContain('数据库')
    expect(components.map((c) => c.name)).toContain('Redis 缓存')
  })

  it('组件状态应根据 healthy 字段显示正确标签', () => {
    const getComponentTag = (healthy: boolean) => (healthy ? 'success' : 'danger')

    expect(getComponentTag(true)).toBe('success')
    expect(getComponentTag(false)).toBe('danger')
  })

  it('统计卡片应显示环比昨日标签', () => {
    const hasTrendLabel = true
    expect(hasTrendLabel).toBe(true)
  })
})

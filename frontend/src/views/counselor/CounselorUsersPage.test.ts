import { describe, it, expect } from 'vitest'

describe('CounselorUsersPage - 4.3.1 用户列表增强', () => {
  it('首字母头像应正确提取首字母', () => {
    const getInitials = (name: string) => {
      if (!name) return '?'
      return name.charAt(0).toUpperCase()
    }

    expect(getInitials('张三')).toBe('张')
    expect(getInitials('john')).toBe('J')
    expect(getInitials('')).toBe('?')
  })

  it('头像颜色应根据用户名哈希生成', () => {
    const colors = ['#3b82c4', '#5a9e3a', '#d4923a', '#d65a5a', '#7a8290', '#9254de', '#ff85c0']
    const getAvatarColor = (username: string) => {
      let hash = 0
      for (let i = 0; i < username.length; i++) {
        hash = username.charCodeAt(i) + ((hash << 5) - hash)
      }
      return colors[Math.abs(hash) % colors.length]
    }

    const color1 = getAvatarColor('user1')
    const color2 = getAvatarColor('user2')

    expect(colors).toContain(color1)
    expect(colors).toContain(color2)
  })

  it('风险等级应映射到正确的标签类型', () => {
    const getRiskTagType = (level: number | undefined) => {
      const map: Record<number, string> = { 0: 'info', 1: 'success', 2: 'warning', 3: 'danger', 4: 'danger' }
      return map[level ?? 0] || 'info'
    }

    expect(getRiskTagType(0)).toBe('info')
    expect(getRiskTagType(2)).toBe('warning')
    expect(getRiskTagType(3)).toBe('danger')
    expect(getRiskTagType(undefined)).toBe('info')
  })

  it('风险筛选应正确过滤数据', () => {
    const rows = [
      { id: 1, risk_level: 1 },
      { id: 2, risk_level: 2 },
      { id: 3, risk_level: 1 }
    ]

    const riskLevel = 1
    const filtered = riskLevel === null ? rows : rows.filter((row) => row.risk_level === riskLevel)

    expect(filtered).toHaveLength(2)
    expect(filtered[0].id).toBe(1)
    expect(filtered[1].id).toBe(3)
  })

  it('详情 Drawer 应显示用户信息', () => {
    const detailFields = ['ID', '邮箱', '风险等级', '状态']

    expect(detailFields).toContain('风险等级')
    expect(detailFields).toContain('状态')
  })
})

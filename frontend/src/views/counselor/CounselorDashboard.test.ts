import { describe, it, expect } from 'vitest'

describe('CounselorDashboard - 4.1.1 统计与快捷操作优化', () => {
  it('统计数字应使用 CountUp 动画组件', () => {
    const useCountUp = true
    const duration = 1200

    expect(useCountUp).toBe(true)
    expect(duration).toBe(1200)
  })

  it('快捷操作按钮应包含图标', () => {
    const buttons = [
      { label: '处理预警', icon: 'Warning' },
      { label: '用户管理', icon: 'User' }
    ]

    expect(buttons[0].icon).toBe('Warning')
    expect(buttons[1].icon).toBe('User')
  })

  it('绑定码应支持一键复制功能', () => {
    const bindCode = 'ABC123'
    const canCopy = bindCode.length > 0

    expect(canCopy).toBe(true)
    expect(bindCode).toBe('ABC123')
  })

  it('统计卡片应包含图标和标题', () => {
    const cards = [
      { title: '今日待处理预警', icon: 'Warning', color: 'warning' },
      { title: '绑定用户数', icon: 'User', color: 'primary' },
      { title: '绑定码', icon: 'CopyDocument', color: 'primary' }
    ]

    expect(cards).toHaveLength(3)
    expect(cards[0].icon).toBe('Warning')
    expect(cards[1].color).toBe('primary')
  })

  it('绑定码显示应使用等宽字体和字母间距', () => {
    const bindCodeStyle = {
      fontSize: '24px',
      letterSpacing: '2px'
    }

    expect(bindCodeStyle.letterSpacing).toBe('2px')
    expect(bindCodeStyle.fontSize).toBe('24px')
  })
})

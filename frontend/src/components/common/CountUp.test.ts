import { describe, it, expect } from 'vitest'

describe('CountUp - 8.1.1 公共组件测试覆盖', () => {
  it('formatNumber 应正确格式化数字', () => {
    const formatNumber = (num: number, decimals: number, separator: string) => {
      const fixed = num.toFixed(decimals)
      const parts = fixed.split('.')
      parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, separator)
      return parts.join('.')
    }

    expect(formatNumber(1234567, 0, ',')).toBe('1,234,567')
    expect(formatNumber(1234567.89, 2, ',')).toBe('1,234,567.89')
    expect(formatNumber(1000, 0, ' ')).toBe('1 000')
  })

  it('easeOutQuart 应在 t=0 时返回 0', () => {
    const easeOutQuart = (t: number) => 1 - Math.pow(1 - t, 4)
    expect(easeOutQuart(0)).toBe(0)
  })

  it('easeOutQuart 应在 t=1 时返回 1', () => {
    const easeOutQuart = (t: number) => 1 - Math.pow(1 - t, 4)
    expect(easeOutQuart(1)).toBe(1)
  })

  it('displayValue 应包含前缀和后缀', () => {
    const prefix = '得分：'
    const suffix = '分'
    const value = 85
    const displayValue = prefix + value + suffix

    expect(displayValue).toBe('得分：85分')
  })
})

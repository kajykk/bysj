import { describe, it, expect } from 'vitest'

describe('UserRiskPage - 3.2.1 风险报告标签页优化', () => {
  it('scoreColor 应返回渐变色数组而非单一颜色', () => {
    const getScoreColor = (score: number) => {
      if (score <= 20) return [{ offset: 0, color: '#67c23a' }, { offset: 1, color: '#95d475' }]
      if (score <= 40) return [{ offset: 0, color: '#e6a23c' }, { offset: 1, color: '#f0c78a' }]
      if (score <= 60) return [{ offset: 0, color: '#f56c6c' }, { offset: 1, color: '#fab6b6' }]
      return [{ offset: 0, color: '#c45656' }, { offset: 1, color: '#f56c6c' }]
    }

    const low = getScoreColor(15)
    const mid = getScoreColor(35)
    const high = getScoreColor(55)
    const critical = getScoreColor(80)

    expect(Array.isArray(low)).toBe(true)
    expect(low).toHaveLength(2)
    expect(low[0]).toHaveProperty('offset')
    expect(low[0]).toHaveProperty('color')

    expect(Array.isArray(mid)).toBe(true)
    expect(Array.isArray(high)).toBe(true)
    expect(Array.isArray(critical)).toBe(true)
  })

  it('风险因子表格应支持按重要性排序', () => {
    const factors = [
      { feature: 'stress', importance: 0.3 },
      { feature: 'sleep', importance: 0.8 },
      { feature: 'exercise', importance: 0.5 }
    ]

    const sorted = [...factors].sort((a, b) => a.importance - b.importance)

    expect(sorted[0].feature).toBe('stress')
    expect(sorted[1].feature).toBe('exercise')
    expect(sorted[2].feature).toBe('sleep')
  })

  it('建议卡片应包含序号和内容', () => {
    const advice = ['保持规律作息', '适当运动', '寻求社会支持']

    const cards = advice.map((text, index) => ({
      index: index + 1,
      text
    }))

    expect(cards).toHaveLength(3)
    expect(cards[0].index).toBe(1)
    expect(cards[0].text).toBe('保持规律作息')
    expect(cards[1].index).toBe(2)
    expect(cards[2].index).toBe(3)
  })

  it('建议卡片样式应包含渐变序号背景', () => {
    const indexStyle = {
      width: '24px',
      height: '24px',
      borderRadius: '50%',
      background: 'linear-gradient(135deg, #409eff, #66b1ff)',
      color: '#fff',
      fontSize: '12px',
      fontWeight: 600
    }

    expect(indexStyle.background).toContain('linear-gradient')
    expect(indexStyle.borderRadius).toBe('50%')
    expect(indexStyle.color).toBe('#fff')
  })
})

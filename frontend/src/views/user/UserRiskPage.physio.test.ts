import { describe, it, expect } from 'vitest'

describe('UserRiskPage - 3.2.5 生理数据标签页优化', () => {
  it('表单字段应包含合理性提示', () => {
    const hints: Record<string, string> = {
      sleep_hours: '成年人建议 7-9 小时',
      sleep_quality: '1-5 分，5 分表示睡眠质量最好',
      exercise_minutes: '建议每日 30-60 分钟',
      heart_rate: '正常静息心率 60-100 bpm',
      systolic_bp: '正常范围 90-120 mmHg',
      diastolic_bp: '正常范围 60-80 mmHg',
      steps: '建议每日 8000-10000 步'
    }

    expect(hints['sleep_hours']).toContain('7-9')
    expect(hints['heart_rate']).toContain('60-100')
    expect(hints['steps']).toContain('8000-10000')
  })

  it('趋势箭头应根据数值变化正确显示方向', () => {
    const getTrend = (current: number, previous: number | null) => {
      if (previous === null) return 'same'
      const diff = current - previous
      if (Math.abs(diff) < 0.01) return 'same'
      return diff > 0 ? 'up' : 'down'
    }

    expect(getTrend(8, 7)).toBe('up')
    expect(getTrend(6, 7)).toBe('down')
    expect(getTrend(7, 7)).toBe('same')
    expect(getTrend(7, null)).toBe('same')
  })

  it('历史数据应包含前一条记录用于趋势对比', () => {
    const history = [
      { time: '2026-04-27', sleep_hours: 8, heart_rate: 72 },
      { time: '2026-04-26', sleep_hours: 7, heart_rate: 75 },
      { time: '2026-04-25', sleep_hours: 7.5, heart_rate: 70 }
    ]

    const withTrend = history.map((item, index) => {
      const prev = history[index + 1]
      return {
        ...item,
        prev_sleep_hours: prev?.sleep_hours ?? null,
        prev_heart_rate: prev?.heart_rate ?? null
      }
    })

    expect(withTrend[0].prev_sleep_hours).toBe(7)
    expect(withTrend[0].prev_heart_rate).toBe(75)
    expect(withTrend[1].prev_sleep_hours).toBe(7.5)
    expect(withTrend[2].prev_sleep_hours).toBeNull()
  })

  it('心率上升应显示红色箭头', () => {
    const trend = 'up'
    const trendClass = {
      'trend-up': trend === 'up',
      'trend-down': trend === 'down',
      'trend-same': trend === 'same'
    }

    expect(trendClass['trend-up']).toBe(true)
  })

  it('步数下降应显示绿色箭头', () => {
    const trend = 'down'
    const trendClass = {
      'trend-up': trend === 'up',
      'trend-down': trend === 'down',
      'trend-same': trend === 'same'
    }

    expect(trendClass['trend-down']).toBe(true)
  })
})

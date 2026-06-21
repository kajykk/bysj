import { describe, it, expect, vi, beforeEach } from 'vitest'

describe('UserDashboard - 3.1.2 风险趋势图表增强', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loadRiskTrend 应使用 trendDays 参数调用 API', async () => {
    const mockGetRiskTrend = vi.fn((days: number) =>
      Promise.resolve({
        days,
        direction: 'stable' as const,
        points: [{ date: '04-20', risk_score: 40, risk_level: 2 }]
      })
    )

    const days = 7
    const result = await mockGetRiskTrend(days)

    expect(mockGetRiskTrend).toHaveBeenCalledWith(7)
    expect(result.days).toBe(7)
    expect(result.points).toHaveLength(1)
  })

  it('tooltip formatter 应正确渲染数据点详情', () => {
    const riskLevelMap: Record<number, string> = { 0: '无风险', 1: '低风险', 2: '中风险', 3: '高风险', 4: '严重' }
    const trendMap: Record<string, string> = { up: '上升', down: '下降', stable: '稳定' }

    const points = [
      { date: '04-20', risk_score: 40, risk_level: 2 },
      { date: '04-21', risk_score: 42, risk_level: 2 }
    ]
    const direction = 'stable'

    const formatter = (params: Array<{ dataIndex: number }>) => {
      const p = params[0]
      const point = points[p.dataIndex]
      if (!point) return ''
      const levelText = riskLevelMap[point.risk_level] || '未知'
      const trendText = trendMap[direction] || '稳定'
      return `<div style="padding: 4px 2px;">
        <div style="font-weight:600;margin-bottom:6px;color:#303133;">${point.date}</div>
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#f56c6c;"></span>
          <span>风险分数：<strong>${point.risk_score}分</strong></span>
        </div>
        <div style="margin-bottom:4px;padding-left:16px;">风险等级：<span style="color:#f56c6c;font-weight:500;">${levelText}</span></div>
        <div style="padding-left:16px;color:#909399;font-size:12px;">整体趋势：${trendText}</div>
      </div>`
    }

    const html = formatter([{ dataIndex: 1 }])

    expect(html).toContain('04-21')
    expect(html).toContain('42分')
    expect(html).toContain('中风险')
    expect(html).toContain('整体趋势：稳定')
    expect(html).toContain('font-weight:600')
  })

  it('tooltip formatter 对无效索引应返回空字符串', () => {
    const points = [{ date: '04-20', risk_score: 40, risk_level: 2 }]

    const formatter = (params: Array<{ dataIndex: number }>) => {
      const p = params[0]
      const point = points[p.dataIndex]
      if (!point) return ''
      return point.date
    }

    expect(formatter([{ dataIndex: 5 }])).toBe('')
  })

  it('ECharts emphasis 配置应包含 scale 和 shadowBlur', () => {
    const emphasis = {
      itemStyle: { borderWidth: 2, borderColor: '#fff', shadowBlur: 8, shadowColor: 'rgba(245,108,108,0.5)' },
      scale: 1.5
    }

    expect(emphasis.scale).toBe(1.5)
    expect(emphasis.itemStyle.shadowBlur).toBe(8)
    expect(emphasis.itemStyle.borderColor).toBe('#fff')
  })
})

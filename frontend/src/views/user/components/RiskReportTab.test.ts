import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RiskReportTab from './RiskReportTab.vue'
import type { RiskReport } from '@/api/userRiskApi'
import i18n from '@/i18n'

// 模拟 ECharts，避免在 jsdom 环境下真实渲染图表
const setOptionMock = vi.fn()
const resizeMock = vi.fn()
const disposeMock = vi.fn()
vi.mock('@/utils/echarts', () => ({
  echarts: {
    init: vi.fn(() => ({
      setOption: setOptionMock,
      resize: resizeMock,
      dispose: disposeMock,
    })),
    graphic: { LinearGradient: vi.fn() },
  },
}))

const sampleReport: RiskReport = {
  risk_score: 55,
  risk_level: 2,
  severity: 'moderate',
  trend: 'up',
  review_required: false,
  crisis_override: false,
  main_factors: [
    { feature: 'stress_level', importance: 0.8, direction: 'positive' },
  ],
  advice: ['保持规律作息', '适当运动'],
} as unknown as RiskReport

const baseProps = {
  report: null,
  loading: false,
  error: '',
  canExport: false,
  trendData: { days: 30, direction: 'stable' as const, points: [] },
}

const mountOptions = {
  global: {
    plugins: [i18n],
  },
}

describe('RiskReportTab', () => {
  beforeEach(() => {
    setOptionMock.mockClear()
    disposeMock.mockClear()
  })

  it('加载状态下应渲染骨架屏而不渲染报告内容', () => {
    const wrapper = mount(RiskReportTab, {
      props: { ...baseProps, loading: true },
      ...mountOptions,
    })
    expect(wrapper.find('.el-skeleton').exists()).toBe(true)
    expect(wrapper.find('.report-score-wrap').exists()).toBe(false)
  })

  it('错误状态下应显示错误信息并在点击重试时触发 retry 事件', async () => {
    const wrapper = mount(RiskReportTab, {
      props: { ...baseProps, error: '加载失败' },
      ...mountOptions,
    })
    expect(wrapper.text()).toContain('加载失败')
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toBeTruthy()
  })

  it('正常报告数据应显示风险分数与严重程度标签', () => {
    const wrapper = mount(RiskReportTab, {
      props: { ...baseProps, report: sampleReport },
      ...mountOptions,
    })
    expect(wrapper.find('.report-score-wrap').exists()).toBe(true)
    expect(wrapper.find('.el-tag').exists()).toBe(true)
    expect(wrapper.text()).toContain('中度')
  })

  it('canExport 为 true 时应显示导出按钮', () => {
    const wrapper = mount(RiskReportTab, {
      props: { ...baseProps, report: sampleReport, canExport: true },
      ...mountOptions,
    })
    expect(wrapper.text()).toContain('导出概览')
  })

  it('canExport 为 false 时不应显示导出按钮', () => {
    const wrapper = mount(RiskReportTab, {
      props: { ...baseProps, report: sampleReport, canExport: false },
      ...mountOptions,
    })
    expect(wrapper.text()).not.toContain('导出概览')
  })

  it('挂载时若存在报告应调用 echarts.init 渲染趋势图', async () => {
    mount(RiskReportTab, {
      props: { ...baseProps, report: sampleReport },
      ...mountOptions,
    })
    await flushPromises()
    expect(setOptionMock).toHaveBeenCalled()
  })

  it('卸载时应调用 dispose 释放图表实例', async () => {
    const wrapper = mount(RiskReportTab, {
      props: { ...baseProps, report: sampleReport },
      ...mountOptions,
    })
    await flushPromises()
    wrapper.unmount()
    expect(disposeMock).toHaveBeenCalled()
  })
})

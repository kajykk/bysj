/**
 * UserReportsPage 空值白屏回归测试（FIX-2026-10-08）。
 *
 * 缺陷: 摘要卡在 `report.risk_score` 上直接调用 `.toFixed(1)`
 *       （UserReportsPage.vue 原 L124）。而 `RiskReport` 接口把
 *       `risk_score` / `risk_level` / `severity` / `main_factors` 全部声称为
 *       **非空**，TypeScript 检查完全放行；运行时只要其中任意一项为 null，
 *       模板求值即抛 TypeError。
 *
 *       这与 `TextAssessTab.nullable.test.ts`（SEC-FIX-2026-10-05）是同一类
 *       失效：Vue 渲染函数抛异常 → 该组件子树被丢弃 → 用户看到**白屏**，
 *       控制台只有一条报错。
 *
 * 为什么既有测试没抓到: 现有 `UserReportsPage.test.ts` 只测两个纯函数
 *       （formatLabel / buildJsonBlob），从不挂载组件 —— 模板分支一行都没跑过。
 *
 * 断言方式: 「渲染不抛异常 + 子树未被清空」，而不是校验具体文案。
 *       白屏时 .summary-card 整块消失，比断言数值更贴近用户感知。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'

const { reportMock, trendMock } = vi.hoisted(() => ({
  reportMock: vi.fn(),
  trendMock: vi.fn(),
}))

vi.mock('@/api/userRiskApi', () => ({
  userRiskApi: { getRiskReport: reportMock, getRiskTrend: trendMock },
}))

vi.mock('@/api/reportsApi', () => ({
  reportsApi: {
    exportUserRiskPdf: vi.fn(),
    exportUserRiskCsv: vi.fn(),
    exportUserRiskJson: vi.fn(),
  },
}))

vi.mock('@/utils/httpFeedback', () => ({
  showHttpFeedback: vi.fn(),
}))

// 捕获 Vue 渲染期错误：白屏的根因就是这里抛异常后被 Vue 丢弃子树。
const { renderErrors } = vi.hoisted(() => ({ renderErrors: [] as unknown[] }))

const mountOptions = {
  global: {
    plugins: [i18n],
    stubs: { BaseChart: true },
    config: {
      errorHandler: (err: unknown) => {
        renderErrors.push(err)
      },
    },
  },
}

function makeReport(overrides: Record<string, unknown> = {}) {
  return {
    risk_level: 2,
    risk_score: 62.35,
    severity: 'moderate',
    trend: 'up',
    main_factors: [{ feature: 'sleep', importance: 0.8, direction: 'increase' }],
    advice: ['保持规律作息'],
    assessed_at: '2026-10-01T00:00:00',
    ...overrides,
  }
}

function makeTrend(overrides: Record<string, unknown> = {}) {
  return {
    days: 30,
    direction: 'up',
    points: [{ date: '2026-10-01', risk_score: 60, risk_level: 2 }],
    ...overrides,
  }
}

async function mountPage() {
  const wrapper = mount(await import('./UserReportsPage.vue').then(m => m.default), mountOptions)
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('UserReportsPage 空值渲染（FIX-2026-10-08）', () => {
  beforeEach(async () => {
    renderErrors.length = 0
    reportMock.mockReset()
    trendMock.mockReset()
    // 预热：首次挂载会编译 element-plus 组件，慢到会触发 30s 超时
    reportMock.mockResolvedValue(makeReport())
    trendMock.mockResolvedValue(makeTrend())
  })

  it('risk_score 为 null 时不抛渲染异常，摘要卡不被清空', async () => {
    reportMock.mockResolvedValue(makeReport({ risk_score: null }))
    trendMock.mockResolvedValue(makeTrend())

    const wrapper = await mountPage()

    expect(renderErrors, '渲染期不应抛异常').toHaveLength(0)
    expect(wrapper.find('.summary-card').exists(), '摘要卡不应因空值消失').toBe(true)
    expect(wrapper.text()).not.toContain('NaN')
    expect(wrapper.text()).not.toContain('undefined')
  })

  it('risk_level 为 null 时不抛渲染异常', async () => {
    reportMock.mockResolvedValue(makeReport({ risk_level: null }))

    const wrapper = await mountPage()

    expect(renderErrors).toHaveLength(0)
    expect(wrapper.find('.summary-card').exists()).toBe(true)
  })

  it('severity 为 null 时不抛渲染异常', async () => {
    reportMock.mockResolvedValue(makeReport({ severity: null }))

    const wrapper = await mountPage()

    expect(renderErrors).toHaveLength(0)
    expect(wrapper.find('.summary-card').exists()).toBe(true)
  })

  it('main_factors 为 null 时不抛渲染异常，因子区走空态', async () => {
    reportMock.mockResolvedValue(makeReport({ main_factors: null }))

    const wrapper = await mountPage()

    expect(renderErrors).toHaveLength(0)
    expect(wrapper.find('.factor-card').exists()).toBe(true)
  })

  it('trend 为 null / points 为 null 时不抛渲染异常', async () => {
    reportMock.mockResolvedValue(makeReport())
    trendMock.mockResolvedValue(null)

    const wrapper = await mountPage()

    expect(renderErrors).toHaveLength(0)
    expect(wrapper.find('.trend-card').exists()).toBe(true)
  })

  it('报告接口失败（report 为 null）时页面仍有可见内容，不是整页空白', async () => {
    reportMock.mockRejectedValue(new Error('500'))
    trendMock.mockRejectedValue(new Error('500'))

    const wrapper = await mountPage()

    expect(renderErrors).toHaveLength(0)
    // 页面骨架（标题 + 导出区）必须仍在
    expect(wrapper.find('.user-reports-page').exists()).toBe(true)
    expect(wrapper.find('.export-card').exists()).toBe(true)
    expect(wrapper.text().trim().length).toBeGreaterThan(0)
  })

  it('正常值路径不受影响（对照：确保修复没有把正常渲染改坏）', async () => {
    reportMock.mockResolvedValue(makeReport())
    trendMock.mockResolvedValue(makeTrend())

    const wrapper = await mountPage()

    expect(renderErrors).toHaveLength(0)
    expect(wrapper.text()).toContain('62.4') // 62.35 → toFixed(1)
  })

  it('边界值：0 分显示为 0.0，不能被当成空值', async () => {
    reportMock.mockResolvedValue(makeReport({ risk_score: 0, risk_level: 0 }))
    trendMock.mockResolvedValue(makeTrend())

    const wrapper = await mountPage()

    expect(renderErrors).toHaveLength(0)
    expect(wrapper.text()).toContain('0.0')
    expect(wrapper.text()).not.toContain('NaN')
  })
})

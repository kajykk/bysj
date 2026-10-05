/**
 * SEC-FIX-2026-10-05: 文本评估结果卡在可空字段上崩溃（白屏丢数据）回归测试。
 *
 * 缺陷:
 *   TextAssessTab.vue 的结果卡直接对 sentiment_score 调用 `.toFixed(2)`，
 *   而后端 backend/app/schemas/model_predict.py:38-39 两者都是 Optional：
 *       sentiment_label: str | None = None
 *       sentiment_score: float | None = None
 *   模型回退路径（如 `model_used="text_heuristic_fallback"`）可能不返回这些字段，
 *   为 null 时模板求值 `null.toFixed(2)` 抛 TypeError。
 *   Vue 渲染函数抛异常 → 该组件子树白屏 → **用户刚提交的分析文本与结果卡一起消失**。
 *
 * 为什么既有测试没抓到:
 *   tests/TextAssessTab.test.ts 的 12 项用例全部只断言 textarea 属性与草稿流程，
 *   从不渲染出「带数据的 v-if 分支」。覆盖率门禁 50% 只统计行覆盖，
 *   未渲染的模板分支根本不计入 → 缺陷长期存活且 CI 全绿。
 *
 * 本文件的断言方式是「**渲染不抛异常**」而非校验具体文案：
 * 白屏时组件树被清空，任何 DOM 断言都会失败，比断言具体值更贴近用户感知。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TextAssessTab from './TextAssessTab.vue'
import i18n from '@/i18n'

const { predictTextMock } = vi.hoisted(() => ({ predictTextMock: vi.fn() }))
vi.mock('@/api/modelApi', () => ({
  modelApi: { predictTextModel: predictTextMock },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: { id: 1, role: 'user' }, role: 'user' }),
}))

const { analyzeTextMock, saveDraftMock, getDraftMock } = vi.hoisted(() => ({
  analyzeTextMock: vi.fn(),
  saveDraftMock: vi.fn(),
  getDraftMock: vi.fn(),
}))
vi.mock('@/api/userApi', () => ({
  userApi: { analyzeText: analyzeTextMock, saveDraft: saveDraftMock, getDraft: getDraftMock },
}))

const { messageSuccessMock, messageErrorMock, messageWarningMock, messageBoxConfirmMock } =
  vi.hoisted(() => ({
    messageSuccessMock: vi.fn(),
    messageErrorMock: vi.fn(),
    messageWarningMock: vi.fn(),
    messageBoxConfirmMock: vi.fn(),
  }))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: {
      success: messageSuccessMock,
      error: messageErrorMock,
      warning: messageWarningMock,
      info: vi.fn(),
    },
    ElMessageBox: { confirm: messageBoxConfirmMock, alert: vi.fn(), prompt: vi.fn() },
  }
})

const mountOptions = {
  global: {
    plugins: [i18n],
    stubs: { 'el-table-column': true },
  },
}

/** 后端 TextPredictResult 的完整形态（Optional 字段可为 null）。 */
function makeResult(overrides: Record<string, unknown> = {}) {
  return {
    prediction: 1,
    probability: 0.8234,
    sentiment_label: 'negative',
    sentiment_score: 0.41,
    model_used: 'tfidf_lr_bilingual',
    ...overrides,
  }
}

/**
 * 触发一次预测：填文本 → 点「模型概览」按钮 → 等待 Promise 链。
 *
 * 注意按钮文案取自 i18n `textAssess.predictBtn`（zh-CN 为「模型概览」），
 * 不能用 /预测|提交/ 模糊匹配 —— 「提交概览」(submitBtn) 是另一个按钮，
 * 误点它不会调用 predictTextModel，结果卡根本不渲染，测试会假通过。
 */
async function runPrediction(wrapper: ReturnType<typeof mount>, text = '最近心情很低落') {
  const textarea = wrapper.find('textarea')
  await textarea.setValue(text)
  const btns = wrapper.findAll('button')
  const predictBtn = btns.find(
    (b) => !b.attributes('disabled') && b.text().replace(/\s+/g, '') === '模型概览',
  )
  expect(predictBtn, '应存在可点击的「模型概览」按钮').toBeTruthy()
  await predictBtn!.trigger('click')
  await flushPromises()
}

describe('TextAssessTab 结果卡可空字段渲染（SEC-FIX-2026-10-05）', () => {
  beforeEach(() => {
    predictTextMock.mockReset()
    analyzeTextMock.mockReset()
    saveDraftMock.mockReset()
    getDraftMock.mockReset()
    messageSuccessMock.mockClear()
    messageErrorMock.mockClear()
    messageWarningMock.mockClear()
    messageBoxConfirmMock.mockReset()
    getDraftMock.mockResolvedValue(null)
    messageBoxConfirmMock.mockResolvedValue(true)
    saveDraftMock.mockResolvedValue({ draft_id: 1 })
    localStorage.clear()
  })

  it('sentiment_score 为 null 时不抛异常且组件树未被清空', async () => {
    predictTextMock.mockResolvedValue(makeResult({ sentiment_score: null }))

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    // 关键断言：结果卡已渲染 —— 白屏时子树会被清空
    // （用标题文案判定，el-result 在当前 stub 下不可靠）
    expect(wrapper.text()).toContain('模型概览结果')
    // 表单主体也应仍在（白屏会一并消失）
    expect(wrapper.find('textarea').exists()).toBe(true)
    // 应显示占位符而不是 NaN
    expect(wrapper.text()).not.toContain('NaN')
  })

  it('sentiment_label 为 null 时不抛异常', async () => {
    predictTextMock.mockResolvedValue(makeResult({ sentiment_label: null }))

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('NaN')
  })

  it('sentiment_score 与 sentiment_label 同时为 null（模型回退路径）也不崩', async () => {
    predictTextMock.mockResolvedValue(
      makeResult({
        sentiment_score: null,
        sentiment_label: null,
        model_used: 'text_heuristic_fallback',
      }),
    )

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('NaN')
  })

  it('概率为 0（边界值）时正常显示 0.00% 而非被误判为空', async () => {
    predictTextMock.mockResolvedValue(makeResult({ probability: 0, sentiment_score: 0 }))

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    expect(wrapper.text()).toContain('0.00')
  })

  it('正常值路径不受影响（对照：确保修复没有把正常渲染改坏）', async () => {
    predictTextMock.mockResolvedValue(makeResult())

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.text()).toContain('82.34') // probability 0.8234 → 82.34%
    expect(wrapper.text()).toContain('0.41') // sentiment_score
    expect(wrapper.text()).toContain('negative')
  })
})

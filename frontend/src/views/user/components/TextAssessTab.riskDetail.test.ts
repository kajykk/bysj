/**
 * P1-前端：文本概览结果卡的「决策依据 / 人工复核」展示回归测试。
 *
 * 背景：融合分此前以「概率」口吻直接展示，用户容易把 0.8 读成
 * 「80% 确诊」。本轮后端在 score_components 里显式标注
 * score_kind = risk_score_not_confidence，并把 ml / heuristic / crisis
 * 三个分量、规则命中与人工复核标记暴露出来；本文件锁定这些字段
 * 确实被渲染，且在旧响应（无新字段）下不崩。
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

function makeScoreComponents(overrides: Record<string, unknown> = {}) {
  return {
    score_kind: 'risk_score_not_confidence',
    ml_probability: 0.8234,
    heuristic_score: 0.45,
    crisis_score: 85,
    model_weight: 0.72,
    heuristic_weight: 0.28,
    model_contribution: 0.5928,
    heuristic_contribution: 0.126,
    disagreement: 0.3734,
    matched_categories: ['passive_ideation'],
    crisis_override: false,
    decision_source: 'fusion',
    ...overrides,
  }
}

function makeResult(overrides: Record<string, unknown> = {}) {
  return {
    prediction: 1,
    probability: 0.8234,
    sentiment_label: 'negative',
    sentiment_score: 0.7188,
    model_used: 'tfidf_lr_bilingual',
    ...overrides,
  }
}

async function runPrediction(wrapper: ReturnType<typeof mount>, text = '最近心情很低落') {
  await wrapper.find('textarea').setValue(text)
  const predictBtn = wrapper
    .findAll('button')
    .find((b) => !b.attributes('disabled') && b.text().replace(/\s+/g, '') === '模型概览')
  expect(predictBtn, '应存在可点击的「模型概览」按钮').toBeTruthy()
  await predictBtn!.trigger('click')
  await flushPromises()
}

function readStoredHistory(): Record<string, unknown>[] {
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i)
    if (key?.startsWith('text_prediction_history_v1_')) {
      return JSON.parse(sessionStorage.getItem(key) ?? '[]')
    }
  }
  return []
}

describe('TextAssessTab 决策依据与人工复核展示（P1）', () => {
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
    sessionStorage.clear()
  })

  it('危机规则命中 + 建议复核 → 显示标签、警示语、分量与规则命中', async () => {
    predictTextMock.mockResolvedValue(
      makeResult({
        crisis_detected: true,
        crisis_keywords: ['不想再继续'],
        suppressed_crisis_keywords: ['想死', '绝望'],
        requires_human_review: true,
        review_reasons: ['crisis_detected', 'crisis_low_confidence'],
        score_components: makeScoreComponents(),
        chunk_info: {
          chunk_count: 3,
          chunk_size: 500,
          chunk_overlap: 80,
          aggregation: 'max',
          chunk_probabilities: [0.8234, 0.1, 0.1],
          chunk_offsets: [[0, 480], [400, 840], [760, 1200]],
        },
        risk_factors: ['无望感', '睡眠问题'],
        protective_factors: ['求助意愿'],
      }),
    )

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    const text = wrapper.text()
    // 头部标签 + 复核警示
    expect(text).toContain('危机规则命中')
    expect(text).toContain('建议人工复核')
    expect(text).toContain('检测到危机相关表述')
    // 结果卡标题必须反映危机状态，不能继续显示绿色「低风险」与警示矛盾
    expect(text).toContain('规则命中危机信号，需人工复核')
    expect(text).not.toContain('模型判定为 0（低风险）')
    expect(text).toContain('ML 模型判定：1（高风险）')
    // 分量单独展示，且明确标注「风险分，不是置信度」
    expect(text).toContain('评分构成')
    expect(text).toContain('风险分，不是置信度')
    expect(text).toContain('模型概率')
    expect(text).toContain('82.3%')
    expect(text).toContain('启发式得分')
    expect(text).toContain('危机规则分')
    expect(text).toContain('模型融合')
    // 长文本分块元数据：让用户知道分数来自哪几段、如何聚合
    expect(text).toContain('长文本分块')
    expect(text).toContain('3 段')
    // 证据区
    expect(text).toContain('风险因素')
    expect(text).toContain('无望感')
    expect(text).toContain('保护因素')
    expect(text).toContain('求助意愿')
    expect(text).toContain('规则命中')
    expect(text).toContain('不想再继续')
    expect(text).toContain('已抑制（否定/转述/讨论词义）')
    expect(text).toContain('想死')
    expect(text).toContain('绝望')
  })

  it('仅高融合分触发复核（无危机规则命中）→ 警告语而不是危机文案', async () => {
    predictTextMock.mockResolvedValue(
      makeResult({
        crisis_detected: false,
        crisis_keywords: [],
        requires_human_review: true,
        review_reasons: ['high_fused_score'],
        score_components: makeScoreComponents({
          crisis_score: 0,
          ml_probability: 0.9,
          heuristic_score: 0.7,
          decision_source: 'fusion',
        }),
        risk_factors: ['情绪低落'],
        protective_factors: [],
      }),
    )

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    const text = wrapper.text()
    expect(text).toContain('建议人工复核')
    expect(text).not.toContain('危机规则命中')
    expect(text).not.toContain('规则命中危机信号')
    expect(text).toContain('融合风险分超过复核阈值')
    expect(text).not.toContain('检测到危机相关表述')
    expect(text).toContain('模型融合')
    expect(text).toContain('无')
  })

  it('模型流历史记录标注 label_source=ml', async () => {
    predictTextMock.mockResolvedValue(makeResult())

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    expect(readStoredHistory()[0]?.label_source).toBe('ml')
  })

  it('日记流历史记录标注 label_source=fused', async () => {
    analyzeTextMock.mockResolvedValue({
      entry_id: 1,
      sentiment_label: 'negative',
      sentiment_score: 0.8,
    })

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await wrapper.find('textarea').setValue('最近心情很低落')
    const submitBtn = wrapper
      .findAll('button')
      .find((b) => b.text().replace(/\s+/g, '') === '提交概览')
    expect(submitBtn, '应存在可点击的「提交概览」按钮').toBeTruthy()
    await submitBtn!.trigger('click')
    await flushPromises()

    expect(readStoredHistory()[0]?.label_source).toBe('fused')
  })

  it('旧响应缺少 score_components / 证据字段 → 不渲染新面板也不报错', async () => {
    predictTextMock.mockResolvedValue(makeResult())

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.text()).toContain('模型概览结果')
    expect(wrapper.text()).not.toContain('评分构成')
    expect(wrapper.text()).not.toContain('建议人工复核')
    expect(wrapper.text()).not.toContain('NaN')
  })
})

describe('TextAssessTab 三态门控与待复核展示（口径统一）', () => {
  beforeEach(() => {
    predictTextMock.mockReset()
    analyzeTextMock.mockReset()
    saveDraftMock.mockResolvedValue({ draft_id: 1 })
    getDraftMock.mockResolvedValue(null)
    localStorage.clear()
    sessionStorage.clear()
  })

  it('normal 态（risk_level=null）→ 显示「未达风险阈值」，不显示「无风险」', async () => {
    predictTextMock.mockResolvedValue(makeResult({
      prediction: 0,
      probability: 0.2,
      risk_level: null,
      text_decision_state: 'normal',
      requires_human_review: false,
    }))

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    const text = wrapper.text()
    expect(text).toContain('未达风险阈值（正常）')
    expect(text).not.toContain('无风险')
  })

  it('suspect 态 → 显示「待复核」并附可读复核原因', async () => {
    predictTextMock.mockResolvedValue(makeResult({
      prediction: 1,
      probability: 0.49,
      risk_level: null,
      text_decision_state: 'suspect',
      requires_human_review: true,
      review_reasons: ['text_suspect_probability'],
    }))

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    const text = wrapper.text()
    expect(text).toContain('待复核（疑似风险）')
    expect(text).toContain('复核原因')
    expect(text).toContain('文本概率处于疑似区间（0.30–0.55）')
    expect(text).not.toContain('无风险')
  })

  it('high_risk 态 → 显示高风险判定状态', async () => {
    predictTextMock.mockResolvedValue(makeResult({
      prediction: 1,
      probability: 0.72,
      risk_level: 3,
      text_decision_state: 'high_risk',
      requires_human_review: true,
      review_reasons: ['text_high_risk_probability'],
    }))

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    expect(wrapper.text()).toContain('高风险（需人工复核）')
    expect(wrapper.text()).toContain('文本概率高于高风险阈值（0.55）')
  })

  it('third_person_matches 非空 → 中性提示，不升级为红色告警', async () => {
    predictTextMock.mockResolvedValue(makeResult({
      prediction: 0,
      probability: 0.2,
      risk_level: null,
      text_decision_state: 'normal',
      third_person_matches: [{ pattern: '我朋友说想死', reason: 'third_person' }],
    }))

    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await runPrediction(wrapper)

    const text = wrapper.text()
    expect(text).toContain('检测到第三方相关表述，未计入本人风险')
    expect(text).toContain('未达风险阈值（正常）')
  })
})

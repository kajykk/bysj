import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import StructuredResultPanel from './StructuredResultPanel.vue'
import i18n from '@/i18n'
import type { ModelPredictResponse } from '@/api/modelApi'

function buildResult(overrides: Partial<ModelPredictResponse> = {}): ModelPredictResponse {
  return {
    risk_score: 62.5,
    risk_level: 3,
    model_used: 'structured_v1.23_external_lr',
    model_version: 'v1.23',
    model_family: 'structured',
    confidence: 0.834,
    fallback_used: false,
    requires_human_review: false,
    safety_flags: [],
    crisis_keywords_matched: [],
    data_quality: {
      missing_fields: [],
      confidence_penalty: 0,
      quality_level: 'complete',
    },
    routing_info: {
      selected_model_id: 'structured_v1.23_external_lr',
      selected_model_family: 'structured',
      routing_reason: 'feature_coverage_sufficient',
      feature_coverage_ratio: 1,
      prediction_confidence_band: 'high',
    },
    thresholds: { mild: 20, moderate: 70, high: 93, critical: 97 },
    threshold_source: 'calibration_v123_p25_p50_p75_p90',
    ...overrides,
  }
}

function mountPanel(result: ModelPredictResponse) {
  return mount(StructuredResultPanel, {
    props: { structuredResult: null, modelTabResult: result },
    global: { plugins: [i18n] },
  })
}

describe('StructuredResultPanel confidence display', () => {
  it('shows the numeric model confidence and labels the routing band as coverage', () => {
    const wrapper = mountPanel(buildResult())
    const text = wrapper.text()
    expect(text).toContain('模型置信度')
    expect(text).toContain('83.4%')
    expect(text).toContain('特征覆盖置信带')
    expect(text).toContain('structured_v1.23_external_lr')
  })

  it('shows a placeholder when confidence is absent', () => {
    const wrapper = mountPanel(buildResult({ confidence: null }))
    expect(wrapper.text()).toContain('模型置信度')
    expect(wrapper.text()).toContain('暂无')
  })
})

describe('StructuredResultPanel score/level alignment', () => {
  it('presents the calibrated level as primary and explains the score band', () => {
    const wrapper = mountPanel(buildResult({ risk_score: 90, risk_level: 2 }))
    const text = wrapper.text()
    // 等级为主
    expect(text).toContain('中度')
    // 分数不再单独裸露：附带等级区间与校准阈值说明
    expect(text).toContain('风险分数：90.00')
    expect(text).toContain('70–92')
    expect(text).toContain('结构化校准阈值 20 / 70 / 93 / 97')
    expect(text).toContain('分数高不等于等级高')
  })

  it('renders null risk_level as pending review instead of "no risk"', () => {
    const wrapper = mountPanel(buildResult({ risk_score: 12, risk_level: null }))
    const text = wrapper.text()
    expect(text).toContain('待复核')
    expect(text).not.toContain('无风险')
    expect(text).toContain('等级尚未判定')
  })
})

describe('StructuredResultPanel threshold single-source', () => {
  it('uses server-provided thresholds for the band text', () => {
    const wrapper = mountPanel(buildResult({
      risk_score: 75,
      risk_level: 2,
      thresholds: { mild: 10, moderate: 60, high: 80, critical: 90 },
    }))
    const text = wrapper.text()
    expect(text).toContain('60–79')
    expect(text).toContain('10 / 60 / 80 / 90')
    // 不能写死本地常量区间
    expect(text).not.toContain('70–92')
    expect(text).not.toContain('本地口径')
  })

  it('falls back to local thresholds and explicitly labels it when thresholds are missing', () => {
    const wrapper = mountPanel(buildResult({
      risk_level: 2,
      thresholds: null,
      threshold_source: null,
    }))
    const text = wrapper.text()
    expect(text).toContain('70–92')
    expect(text).toContain('20 / 70 / 93 / 97')
    expect(text).toContain('本地口径，服务端未下发')
  })

  it('shows a neutral fallback notice when threshold_source is fallback', () => {
    const wrapper = mountPanel(buildResult({
      risk_level: 2,
      thresholds: { mild: 5, moderate: 50, high: 70, critical: 85 },
      threshold_source: 'fallback',
    }))
    const text = wrapper.text()
    expect(text).toContain('当前为兜底评分口径')
    expect(text).toContain('50–69')
    expect(text).toContain('5 / 50 / 70 / 85')
  })
})

describe('StructuredResultPanel input adjustments', () => {
  it('shows an informational hint when values were clamped', () => {
    const wrapper = mountPanel(buildResult({
      input_adjustments: {
        clamped_fields: [{ field: 'stress_level', original: 5, value: 4 }],
      },
    }))
    const text = wrapper.text()
    expect(text).toContain('部分输入已按模型范围自动修正')
    expect(text).toContain('压力水平')
    expect(text).toContain('已按上限处理')
  })

  it('shows an informational hint when missing fields were neutralized', () => {
    const wrapper = mountPanel(buildResult({
      defaulted_missing_fields: [{ field: 'academic_pressure', value: 0 }],
    }))
    const text = wrapper.text()
    expect(text).toContain('部分输入已按模型范围自动修正')
    expect(text).toContain('学业压力')
    expect(text).toContain('未填写，已按中性值处理')
  })

  it('hides the hint when nothing was adjusted', () => {
    const wrapper = mountPanel(buildResult())
    expect(wrapper.text()).not.toContain('部分输入已按模型范围自动修正')
  })
})

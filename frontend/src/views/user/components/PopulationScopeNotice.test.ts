import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PopulationScopeNotice from './PopulationScopeNotice.vue'
import i18n from '@/i18n'
import type { PopulationScope } from '@/api/modelApi'

function buildScope(overrides: Partial<PopulationScope> = {}): PopulationScope {
  return {
    scope_version: '2026-11-02',
    population_id: 'students_self_report_v1_23',
    population_label: '学生/青年自报问卷人群',
    language: 'en',
    setting: '在线自报问卷',
    label_definition: '自报二分类，不是临床诊断',
    validation_cohort: '内部测试 n=4318；跨来源 n=682',
    evidence_level: 'internal_source_split',
    transport_risk: 'degraded',
    calibration_scope: '跨来源未重新校准',
    intended_use: '筛查辅助与人工复核排序',
    out_of_scope: ['非学生成人', '临床诊断'],
    automated_decision_allowed: false,
    abstention_recommended: true,
    abstention_reasons: ['尚无目标域校准', '证据仅覆盖登记人群'],
    disclosure: '不得用于自动决策',
    ...overrides,
  }
}

function mountNotice(scope: PopulationScope | null) {
  return mount(PopulationScopeNotice, {
    props: { scope },
    global: { plugins: [i18n] },
  })
}

describe('PopulationScopeNotice', () => {
  it('renders the registered population, evidence level and abstention disclosure', () => {
    const text = mountNotice(buildScope()).text()
    expect(text).toContain('验证范围与适用人群')
    expect(text).toContain('同源内部切分（仅限登记人群）')
    expect(text).toContain('禁止自动决策')
    expect(text).toContain('学生/青年自报问卷人群')
    expect(text).toContain('非学生成人')
    expect(text).toContain('尚无目标域校准')
  })

  it('localizes fallback evidence and keeps automated decisions disabled', () => {
    const text = mountNotice(
      buildScope({
        evidence_level: 'heuristic_fallback',
        transport_risk: 'not_evaluated',
      })
    ).text()
    expect(text).toContain('启发式回退（未经模型验证）')
    expect(text).toContain('禁止自动决策')
  })

  it('localizes synthetic label-derived evidence and shows the provenance caveat', () => {
    const text = mountNotice(
      buildScope({
        evidence_level: 'synthetic_label_derived',
        abstention_reasons: ['训练特征 5/7 为标签驱动合成'],
      })
    ).text()
    expect(text).toContain('标签驱动合成特征（非真实测量）')
    expect(text).toContain('训练特征 5/7 为标签驱动合成')
    expect(text).toContain('禁止自动决策')
  })

  it('renders nothing without a scope', () => {
    expect(mountNotice(null).find('.population-scope').exists()).toBe(false)
  })
})

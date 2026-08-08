// frontend/src/views/user/components/structured-steps/sharedStepUtils.test.ts
import { describe, it, expect } from 'vitest'
import { formatWarningGenerated } from './sharedStepUtils'
import i18n from '@/i18n'

const t = (key: string) => i18n.global.t(key)

describe('formatWarningGenerated - PERF-P1-004 三态渲染', () => {
  it('true → 是/Yes', () => {
    expect(formatWarningGenerated(true, 'option')).toBe(t('structuredAssess.yesOption'))
    expect(formatWarningGenerated(true, 'csv')).toBe(t('structuredAssess.csvYes'))
  })

  it('false → 否/No', () => {
    expect(formatWarningGenerated(false, 'option')).toBe(t('structuredAssess.noOption'))
    expect(formatWarningGenerated(false, 'csv')).toBe(t('structuredAssess.csvNo'))
  })

  it('null(异步待定) → 处理中/Processing，而非误判为"否"', () => {
    expect(formatWarningGenerated(null, 'option')).toBe(t('structuredAssess.warningPending'))
    expect(formatWarningGenerated(null, 'csv')).toBe(t('structuredAssess.csvPending'))
  })

  it('undefined 按待定处理', () => {
    expect(formatWarningGenerated(undefined, 'option')).toBe(t('structuredAssess.warningPending'))
  })
})
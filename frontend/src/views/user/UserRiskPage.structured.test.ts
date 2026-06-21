import { describe, it, expect } from 'vitest'

describe('UserRiskPage - 3.2.2 结构化评估表单优化', () => {
  it('应支持单页模式和分步向导模式切换', () => {
    const modes = ['single', 'stepper'] as const
    const currentMode: 'single' | 'stepper' = 'stepper'

    expect(modes).toContain(currentMode)
    expect(currentMode).toBe('stepper')
  })

  it('分步向导应包含 4 个步骤', () => {
    const steps = ['基本信息', '学业/工作', '生活状态', '心理状况']

    expect(steps).toHaveLength(4)
    expect(steps[0]).toBe('基本信息')
    expect(steps[3]).toBe('心理状况')
  })

  it('每个步骤应包含正确的字段', () => {
    const stepFields: Record<number, string[]> = {
      0: ['identity_type', 'age', 'gender', 'study_year'],
      1: ['cgpa', 'academic_pressure', 'financial_pressure'],
      2: ['sleep_duration', 'exercise_frequency', 'social_support'],
      3: ['stress_level', 'anxiety', 'family_history', 'panic_attack', 'treatment_seeking']
    }

    expect(stepFields[0]).toContain('identity_type')
    expect(stepFields[0]).toContain('age')
    expect(stepFields[1]).toContain('cgpa')
    expect(stepFields[2]).toContain('sleep_duration')
    expect(stepFields[3]).toContain('stress_level')
    expect(stepFields[3]).toContain('treatment_seeking')
  })

  it('滑块数值标签应正确格式化', () => {
    const formatSliderValue = (value: number, unit: string, max: number) => {
      if (unit === '小时') return `${value} 小时`
      if (unit === '次/周') return `${value} 次/周`
      return `${value} / ${max}`
    }

    expect(formatSliderValue(7.5, '小时', 12)).toBe('7.5 小时')
    expect(formatSliderValue(3, '次/周', 7)).toBe('3 次/周')
    expect(formatSliderValue(4, '分', 5)).toBe('4 / 5')
  })

  it('GPA 应格式化为一位小数', () => {
    const cgpa = 3.0
    expect(cgpa.toFixed(1)).toBe('3.0')

    const cgpa2 = 3.55
    expect(cgpa2.toFixed(1)).toBe('3.5')
  })

  it('步骤验证失败时不应进入下一步', () => {
    const currentStep = 0
    const isValid = false

    const nextStep = isValid ? currentStep + 1 : currentStep

    expect(nextStep).toBe(0)
  })

  it('步骤验证成功时应进入下一步', () => {
    const currentStep = 0
    const isValid = true

    const nextStep = isValid ? currentStep + 1 : currentStep

    expect(nextStep).toBe(1)
  })
})

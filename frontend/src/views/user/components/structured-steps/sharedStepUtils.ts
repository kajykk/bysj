// StructuredForm 接口（14 字段）
import i18n from '@/i18n'

export interface StructuredForm {
  identity_type: string
  age: number
  gender: number
  study_year: number
  cgpa: number
  academic_pressure: number
  financial_pressure: number
  sleep_duration: number
  exercise_frequency: number
  social_support: number
  stress_level: number
  anxiety: number
  family_history: number
  panic_attack: number
  treatment_seeking: number
}

// 默认表单值（从源文件 877-891 行提取）
export const DEFAULT_STRUCTURED_FORM: StructuredForm = {
  identity_type: 'student',
  age: 20,
  gender: 1,
  study_year: 2,
  cgpa: 3.0,
  academic_pressure: 3,
  financial_pressure: 2,
  sleep_duration: 7,
  exercise_frequency: 3,
  social_support: 3,
  stress_level: 3,
  anxiety: 3,
  family_history: 0,
  panic_attack: 0,
  treatment_seeking: 0,
}

// 步骤字段映射（从源文件 995-1000 行提取）
export const STEP_FIELDS: Record<number, string[]> = {
  0: ['identity_type', 'age', 'gender', 'study_year'],
  1: ['cgpa', 'academic_pressure', 'financial_pressure'],
  2: ['sleep_duration', 'exercise_frequency', 'social_support'],
  3: ['stress_level', 'anxiety', 'family_history', 'panic_attack', 'treatment_seeking'],
}

// 滑块值格式化（补齐 UserRiskPage.structured.test.ts 中预期的函数）
export function formatSliderValue(value: number, unit: string, max: number): string {
  if (unit === '小时') return `${value} 小时`
  if (unit === '次/周') return `${value} 次/周`
  return `${value} / ${max}`
}

// PERF-P1-004 三态：warning_generated 为 boolean|null。
// - true → csvYes, false → csvNo, null → csvPending(处理中)
// 供结果面板、历史表格、CSV 导出三处共用，确保展示一致。
const t = i18n.global.t.bind(i18n.global)

export function formatWarningGenerated(
  value: boolean | null | undefined,
  kind: 'option' | 'csv' = 'option',
): string {
  const yes = kind === 'csv' ? t('structuredAssess.csvYes') : t('structuredAssess.yesOption')
  const no = kind === 'csv' ? t('structuredAssess.csvNo') : t('structuredAssess.noOption')
  const pending =
    kind === 'csv' ? t('structuredAssess.csvPending') : t('structuredAssess.warningPending')
  if (value === true) return yes
  if (value === false) return no
  return pending
}

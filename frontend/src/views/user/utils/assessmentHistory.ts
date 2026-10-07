/**
 * 评估历史列表的「后端契约 → 表格行」映射层。
 *
 * FIX-2026-10-08（表格契约错配）：
 *
 * 缺陷: UserAssessmentsPage 的 6 个 el-table-column 用的是 `assessment_type`
 *       / `score` / `risk_level` / `summary`，而列表数据源 `GET /user/data/history`
 *       返回的每一项是 `DataHistoryItem { id, type, created_at, data }`
 *       （后端字面量见 backend/app/services/user_data_service.py:371-384 /
 *       408-422 / 448-464）。`assessment_type`、`risk_level`、`summary` 在该
 *       契约里**根本不存在**，`score` 也不在顶层 —— 于是「得分/风险等级/摘要」
 *       三列恒为空白，只剩 id 与时间有值。
 *
 *       同一页面内还并存第二套契约：`handleExport`（原 L286-293）导出用的却是
 *       `type` / `created_at` / `data`，即**同一页里两套字段名**，直接自证错配。
 *
 *       更隐蔽的是类型层面：`rows` 被声明为 `AssessmentRecordItem[]`
 *       （`/user/risk/assessments/{id}` 详情端点的形状），实际赋的是
 *       `DataHistoryItem[]`，靠 `as unknown as` 绕过检查 —— vue-tsc 永远不会报错。
 *
 * 为什么必须抽成纯函数: 表格列的取值规则分散在模板里就无法单测，只能靠肉眼；
 *       抽出来后「后端契约 → 单元格文本」的全部规则都能被断言覆盖。
 *
 * 取值口径（按后端 models/assessment.py 的实际列）:
 *   - structured: data.score (Float, 0-100) / data.severity / data.assessment_type
 *   - text:       data.content / data.mood_score / data.sentiment_score / data.sentiment_label
 *   - physiological: data.source / data.sleep_hours / data.sleep_quality /
 *                    data.exercise_minutes / data.heart_rate / data.steps
 *
 * 量纲纪律: text 的 sentiment_score 是 0-1 情绪分、physiological 没有风险分，
 *       与 structured 的 0-100 风险分**不可比**。混合填进同一「得分」列会误导
 *       （临床场景里 0.8 会被读成「风险 0.8 分」），因此非 structured 记录
 *       的得分列显示 `-`，其关键信息改由「摘要」列承载。
 */

import { formatDate } from '@/utils/formatUtils'
import { severityLabel } from '@/utils/riskFormatters'
import type { DataHistoryItem } from '@/api/userTypes'

/** 单元格占位符，与 formatUtils.formatDate 的 '-' 保持一致。 */
export const NO_VALUE = '-'

export interface AssessmentHistoryRow {
  id: number
  /** 后端 `type` 原值（structured / text / physiological），供页面做 i18n 标签映射。 */
  type: string
  /** 已格式化的得分文本；无同量纲分数时为 '-'。 */
  score: string
  /** 已翻译的风险等级文本；不可判定为 '-'。 */
  riskLevel: string
  /** 按类型提炼的摘要文本。 */
  summary: string
  /** 已格式化的时间文本。 */
  createdAt: string
}

export interface AssessmentHistoryStats {
  total: number
  structured: number
  text: number
  physiological: number
  highRisk: number
  mediumRisk: number
  lowRisk: number
}

/** 窄化数字：拒绝 NaN / Infinity / 空串 / 布尔，避免把脏值当分数渲染出去。 */
function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'boolean') return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function payloadOf(item: DataHistoryItem): Record<string, unknown> {
  return item && typeof item.data === 'object' && item.data !== null ? item.data : {}
}

function firstText(payload: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const raw = payload[key]
    if (typeof raw === 'string' && raw.trim() !== '') return raw.trim()
    if (typeof raw === 'number' && Number.isFinite(raw)) return String(raw)
  }
  return ''
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}…` : text
}

/**
 * 结构化评估：0-100 风险分。
 * 其余类型没有可比的 0-100 风险分，返回 null（由调用方显示 '-'）。
 */
export function extractScore(item: DataHistoryItem): number | null {
  if (item?.type !== 'structured') return null
  return toFiniteNumber(payloadOf(item).score)
}

/** 风险等级文本。当前契约下结构化记录只有 `severity` 字符串，无数字等级。 */
export function extractRiskLevelText(item: DataHistoryItem): string {
  if (item?.type !== 'structured') return NO_VALUE
  const severity = payloadOf(item).severity
  const text = typeof severity === 'string' ? severity.trim() : ''
  return text ? severityLabel(text) : NO_VALUE
}

/** 按类型提炼摘要，保证三列不再恒空。 */
export function buildSummary(item: DataHistoryItem): string {
  const payload = payloadOf(item)
  switch (item?.type) {
    case 'text': {
      const content = firstText(payload, ['content'])
      if (content) return truncate(content, 60)
      const label = firstText(payload, ['sentiment_label'])
      return label || NO_VALUE
    }
    case 'physiological': {
      const parts: string[] = []
      const source = firstText(payload, ['source'])
      if (source) parts.push(source)
      const sleep = toFiniteNumber(payload.sleep_hours)
      if (sleep !== null) parts.push(`睡眠 ${sleep}h`)
      const exercise = toFiniteNumber(payload.exercise_minutes)
      if (exercise !== null) parts.push(`运动 ${exercise}min`)
      const heartRate = toFiniteNumber(payload.heart_rate)
      if (heartRate !== null) parts.push(`心率 ${heartRate}`)
      const steps = toFiniteNumber(payload.steps)
      if (steps !== null) parts.push(`步数 ${steps}`)
      return parts.length ? parts.join(' · ') : NO_VALUE
    }
    case 'structured': {
      const parts: string[] = []
      const subType = firstText(payload, ['assessment_type'])
      if (subType) parts.push(subType)
      const severity = firstText(payload, ['severity'])
      if (severity) parts.push(severityLabel(severity))
      return parts.length ? parts.join(' · ') : NO_VALUE
    }
    default:
      return NO_VALUE
  }
}

export function toAssessmentHistoryRow(item: DataHistoryItem): AssessmentHistoryRow {
  const score = extractScore(item)
  return {
    id: item?.id,
    type: item?.type ?? '',
    score: score === null ? NO_VALUE : String(score),
    riskLevel: extractRiskLevelText(item),
    summary: buildSummary(item),
    createdAt: formatDate(item?.created_at),
  }
}

export function toAssessmentHistoryRows(
  items: DataHistoryItem[] | null | undefined
): AssessmentHistoryRow[] {
  return (items || []).map(toAssessmentHistoryRow)
}

/** 统计卡用的分布统计。风险分档只统计有 0-100 风险分的结构化记录。 */
export function summarizeAssessmentHistory(
  items: DataHistoryItem[] | null | undefined
): AssessmentHistoryStats {
  const stats: AssessmentHistoryStats = {
    total: 0,
    structured: 0,
    text: 0,
    physiological: 0,
    highRisk: 0,
    mediumRisk: 0,
    lowRisk: 0,
  }
  for (const item of items || []) {
    stats.total += 1
    if (item?.type === 'structured') stats.structured += 1
    else if (item?.type === 'text') stats.text += 1
    else if (item?.type === 'physiological') stats.physiological += 1

    const score = extractScore(item)
    if (score === null) continue
    // 分档与后端 RISK_LEVEL_THRESHOLDS (backend/app/core/risk_thresholds.py:
    // mild 22 / moderate 42 / high 62 / critical 82) 的 score_to_level 对齐。
    if (score >= 62) stats.highRisk += 1
    else if (score >= 42) stats.mediumRisk += 1
    else if (score >= 22) stats.lowRisk += 1
  }
  return stats
}

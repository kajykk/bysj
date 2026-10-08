/**
 * 评估历史契约映射的单测。
 *
 * 这些断言直接对应「表格契约错配」缺陷：改前的模板用 assessment_type /
 * risk_level / summary / 顶层 score 取值，而后端 `GET /user/data/history`
 * 返回的是 `{ id, type, created_at, data }`，四项里三项恒空。
 * 本文件用后端真实形状构造输入，逐列断言单元格文本。
 */
import { describe, it, expect } from 'vitest'
import type { DataHistoryItem } from '@/api/userTypes'
import {
  NO_VALUE,
  buildDetailFields,
  buildSummary,
  extractFullText,
  extractRawPayload,
  extractRiskLevelText,
  extractScore,
  summarizeAssessmentHistory,
  toAssessmentHistoryRow,
  toAssessmentHistoryRows,
} from './assessmentHistory'

function structured(overrides: Partial<DataHistoryItem> = {}): DataHistoryItem {
  return {
    id: 11,
    type: 'structured',
    created_at: '2026-10-01T08:30:00',
    data: { assessment_type: 'PHQ-9', score: 72.5, severity: 'high', data_payload: { q1: 3 } },
    ...overrides,
  } as DataHistoryItem
}

function text(overrides: Partial<DataHistoryItem> = {}): DataHistoryItem {
  return {
    id: 12,
    type: 'text',
    created_at: '2026-10-02T09:00:00',
    data: {
      entry_type: 'diary',
      content: '最近两周睡眠很差，白天注意力难以集中，情绪低落。',
      mood_score: 3,
      sentiment_score: 0.21,
      sentiment_label: 'negative',
    },
    ...overrides,
  } as DataHistoryItem
}

function physio(overrides: Partial<DataHistoryItem> = {}): DataHistoryItem {
  return {
    id: 13,
    type: 'physiological',
    created_at: '2026-10-03T07:00:00',
    data: {
      source: 'wearable',
      sleep_hours: 5.5,
      exercise_minutes: 20,
      heart_rate: 88,
      steps: 4200,
    },
    ...overrides,
  } as DataHistoryItem
}

describe('toAssessmentHistoryRow —— 后端契约映射', () => {
  it('structured: 得分取 data.score（0-100 风险分），不是顶层 score', () => {
    const row = toAssessmentHistoryRow(structured())
    expect(row.score).toBe('72.5')
    expect(row.type).toBe('structured')
    expect(row.id).toBe(11)
  })

  it('structured: 风险等级取 data.severity，而不是不存在的 risk_level', () => {
    expect(toAssessmentHistoryRow(structured()).riskLevel).not.toBe(NO_VALUE)
    expect(
      toAssessmentHistoryRow(structured({ data: { score: 10, severity: null } })).riskLevel
    ).toBe(NO_VALUE)
  })

  it('structured: 摘要含子类型与严重程度，不再恒空', () => {
    expect(toAssessmentHistoryRow(structured()).summary).toContain('PHQ-9')
  })

  it('text: 摘要取 data.content 截断，得分列因为量纲不可比显示占位符', () => {
    const row = toAssessmentHistoryRow(text())
    expect(row.summary).toContain('最近两周睡眠很差')
    expect(row.summary.length).toBeLessThanOrEqual(61)
    expect(row.score).toBe(NO_VALUE)
    expect(row.riskLevel).toBe(NO_VALUE)
  })

  it('physiological: 摘要聚合睡眠/运动/心率/步数', () => {
    const summary = toAssessmentHistoryRow(physio()).summary
    expect(summary).toContain('wearable')
    expect(summary).toContain('睡眠 5.5h')
    expect(summary).toContain('步数 4200')
  })

  it('时间列格式化 created_at，而不是 undefined', () => {
    expect(toAssessmentHistoryRow(structured()).createdAt).not.toBe(NO_VALUE)
    expect(toAssessmentHistoryRow(structured()).createdAt).toMatch(/2026-10-01/)
  })

  it('空 data / null 字段不抛异常，退化成占位符', () => {
    expect(() =>
      toAssessmentHistoryRow({ id: 1, type: 'structured', created_at: '', data: {} })
    ).not.toThrow()
    expect(
      toAssessmentHistoryRow({ id: 1, type: 'structured', created_at: '', data: {} }).score
    ).toBe(NO_VALUE)
    expect(buildSummary({ id: 1, type: 'unknown-type', created_at: '', data: {} })).toBe(NO_VALUE)
  })

  it('脏分数（NaN/Infinity/字符串数字/布尔）被拒绝而不是原样渲染', () => {
    expect(extractScore(structured({ data: { score: Number.NaN } }))).toBeNull()
    expect(extractScore(structured({ data: { score: Number.POSITIVE_INFINITY } }))).toBeNull()
    expect(extractScore(structured({ data: { score: true } }))).toBeNull()
    expect(extractScore(structured({ data: { score: '45' } }))).toBe(45)
  })

  it('0 分是合法值，不能被当成空', () => {
    expect(extractScore(structured({ data: { score: 0 } }))).toBe(0)
    expect(toAssessmentHistoryRow(structured({ data: { score: 0 } })).score).toBe('0')
  })

  it('批量映射保持顺序', () => {
    const rows = toAssessmentHistoryRows([structured(), text(), physio()])
    expect(rows.map(r => r.id)).toEqual([11, 12, 13])
    expect(toAssessmentHistoryRows(null)).toEqual([])
  })
})

describe('summarizeAssessmentHistory —— 统计卡', () => {
  it('按 type 正确分类（改前用 assessment_type 统计，三类恒为 0）', () => {
    const stats = summarizeAssessmentHistory([
      structured(),
      structured({ id: 2 }),
      text(),
      physio(),
    ])
    expect(stats.total).toBe(4)
    expect(stats.structured).toBe(2)
    expect(stats.text).toBe(1)
    expect(stats.physiological).toBe(1)
  })

  it('风险分档按后端阈值（62/42/22）统计（改前用 risk_level 统计，三项恒为 0）', () => {
    const stats = summarizeAssessmentHistory([
      structured({ id: 1, data: { score: 80 } }),
      structured({ id: 2, data: { score: 65 } }),
      structured({ id: 3, data: { score: 50 } }),
      structured({ id: 4, data: { score: 30 } }),
      structured({ id: 5, data: { score: 10 } }),
    ])
    expect(stats.highRisk).toBe(2)
    expect(stats.mediumRisk).toBe(1)
    expect(stats.lowRisk).toBe(1)
  })

  it('阈值边界：62 归入高风险、42 归入中风险、22 归入低风险', () => {
    const stats = summarizeAssessmentHistory([
      structured({ id: 1, data: { score: 62 } }),
      structured({ id: 2, data: { score: 42 } }),
      structured({ id: 3, data: { score: 22 } }),
    ])
    expect(stats.highRisk).toBe(1)
    expect(stats.mediumRisk).toBe(1)
    expect(stats.lowRisk).toBe(1)
  })

  it('text/physiological 不参与风险分档（量纲不可比）', () => {
    const stats = summarizeAssessmentHistory([text(), physio()])
    expect(stats.highRisk + stats.mediumRisk + stats.lowRisk).toBe(0)
  })

  it('空输入返回全 0 而不是抛异常', () => {
    expect(summarizeAssessmentHistory(null)).toEqual({
      total: 0,
      structured: 0,
      text: 0,
      physiological: 0,
      highRisk: 0,
      mediumRisk: 0,
      lowRisk: 0,
    })
  })
})

describe('extractRiskLevelText —— 等级文案', () => {
  it('未知 severity 退化为占位符而不是 "unknown" 原文', () => {
    expect(extractRiskLevelText(text())).toBe(NO_VALUE)
  })
})

// 详情页本地渲染（FIX-2026-10-08）
describe('buildDetailFields —— 详情页字段展开', () => {
  it('structured：只补充展开「量表」，不与通用行的得分/风险等级重复', () => {
    expect(buildDetailFields(structured())).toEqual([{ label: 'assessmentType', value: 'PHQ-9' }])
  })

  it('text：展开记录类型/心情/情绪分/情绪倾向', () => {
    expect(buildDetailFields(text()).map(f => f.label)).toEqual([
      'entryType',
      'moodScore',
      'sentimentScore',
      'sentimentLabel',
    ])
  })

  it('snake_case 的后端键一律转成 camelCase（i18n 键规范强制）', () => {
    for (const label of buildDetailFields(structured()).map(f => f.label)) {
      expect(label).not.toMatch(/_/)
    }
  })

  it('只输出载荷里真实存在的字段，不给可空列排一排 "-"', () => {
    const item = structured({
      data: { assessment_type: 'PHQ-9', score: null, severity: undefined },
    } as Partial<DataHistoryItem>)
    expect(buildDetailFields(item)).toEqual([{ label: 'assessmentType', value: 'PHQ-9' }])
  })

  it('text 的 mood_score 为 0 是合法值，必须保留（不能用真值判断过滤掉）', () => {
    const item = text({ data: { entry_type: 'diary', mood_score: 0 } } as Partial<DataHistoryItem>)
    expect(buildDetailFields(item)).toEqual([
      { label: 'entryType', value: 'diary' },
      { label: 'moodScore', value: '0' },
    ])
  })

  it('未知类型不臆造字段（返回空数组而不是把整个载荷倒出来）', () => {
    expect(buildDetailFields({ id: 1, type: 'mystery', created_at: '', data: { a: 1 } })).toEqual(
      []
    )
  })

  it('NaN 分数不出现在详情里', () => {
    const item = structured({ data: { score: Number.NaN } } as Partial<DataHistoryItem>)
    // toFiniteNumber 只认有限数；NaN 走 String() 会变成 "NaN"，这里显式拒绝
    expect(buildDetailFields(item).map(f => f.value)).not.toContain('NaN')
  })
})

describe('extractFullText / extractRawPayload —— 详情页的独占内容', () => {
  it('text：给出 content 全文（列表里是截断到 60 字的摘要）', () => {
    const long =
      '最近两周睡眠很差，几乎每天凌晨两三点才睡着，白天上课完全集中不了注意力，' +
      '和室友的交流也变少了，感觉自己什么都做不好，情绪越来越低落，有时候会忍不住哭，' +
      '但又不知道怎么开口求助。'
    const item = text({ data: { content: long } } as Partial<DataHistoryItem>)
    expect(extractFullText(item)).toBe(long)
    expect(buildSummary(item).length).toBeLessThan(long.length)
  })

  it('非 text 类型没有全文', () => {
    expect(extractFullText(structured())).toBe('')
  })

  it('structured：data_payload 美化输出', () => {
    expect(extractRawPayload(structured())).toBe('{\n  "q1": 3\n}')
  })

  it('data_payload 为 null 时返回空串而不是 "null"', () => {
    expect(
      extractRawPayload(structured({ data: { data_payload: null } } as Partial<DataHistoryItem>))
    ).toBe('')
  })
})

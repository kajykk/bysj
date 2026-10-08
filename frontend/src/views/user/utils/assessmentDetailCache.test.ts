/**
 * 详情页 sessionStorage 快照单测（FIX-2026-10-08）。
 *
 * 这个模块是「新标签页打开详情链接」的兜底路径，全部行为都必须在
 * 隐私模式（sessionStorage 不可用）、JSON 损坏、配额超限等异常下
 * **静默降级** —— 主路径（history.state）不受影响才是它的设计目的。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { DataHistoryItem } from '@/api/userTypes'
import {
  CACHE_KEY,
  clearAssessmentDetailCache,
  readCachedAssessmentItem,
  writeAssessmentDetailCache,
} from './assessmentDetailCache'

const item = (id: number): DataHistoryItem => ({
  id,
  type: 'structured',
  created_at: '2026-10-01T08:30:00',
  data: { score: 72.5 },
})

describe('assessmentDetailCache —— 详情页快照', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
  })

  it('写入后能按 id 取回', () => {
    writeAssessmentDetailCache([item(11), item(12)])
    expect(readCachedAssessmentItem(CACHE_KEY, 12)?.id).toBe(12)
  })

  it('空列表写入会清掉旧快照（切页/筛选后不该残留上一页）', () => {
    writeAssessmentDetailCache([item(11)])
    writeAssessmentDetailCache([])
    expect(readCachedAssessmentItem(CACHE_KEY, 11)).toBeNull()
  })

  it('快照里没有该 id 时返回 null，不拿邻近记录顶替', () => {
    writeAssessmentDetailCache([item(12)])
    expect(readCachedAssessmentItem(CACHE_KEY, 11)).toBeNull()
  })

  it('JSON 损坏时不抛异常，降级为无快照', () => {
    window.sessionStorage.setItem(CACHE_KEY, '{not json')
    expect(() => readCachedAssessmentItem(CACHE_KEY, 11)).not.toThrow()
    expect(readCachedAssessmentItem(CACHE_KEY, 11)).toBeNull()
  })

  it('快照不是数组时不抛异常', () => {
    window.sessionStorage.setItem(CACHE_KEY, '{"id":11}')
    expect(readCachedAssessmentItem(CACHE_KEY, 11)).toBeNull()
  })

  it('sessionStorage 写满（配额超限）时不抛异常', () => {
    const failing = {
      getItem: () => null,
      setItem: () => {
        throw new Error('QuotaExceededError')
      },
      removeItem: () => {},
    }
    vi.stubGlobal('sessionStorage', failing)
    expect(() => writeAssessmentDetailCache([item(11)])).not.toThrow()
    vi.unstubAllGlobals()
  })

  it('sessionStorage 整体不可用时读写都不炸（隐私模式）', () => {
    const boom = () => {
      throw new Error('SecurityError')
    }
    vi.stubGlobal('sessionStorage', { getItem: boom, setItem: boom, removeItem: boom })
    expect(() => writeAssessmentDetailCache([item(11)])).not.toThrow()
    expect(readCachedAssessmentItem(CACHE_KEY, 11)).toBeNull()
    expect(() => clearAssessmentDetailCache()).not.toThrow()
    vi.unstubAllGlobals()
  })

  it('超过上限时截断而不是把 sessionStorage 撑爆', () => {
    const items = Array.from({ length: 150 }, (_, i) => item(i + 1))
    writeAssessmentDetailCache(items)
    const raw = window.sessionStorage.getItem(CACHE_KEY)
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!).length).toBeLessThanOrEqual(100)
    expect(readCachedAssessmentItem(CACHE_KEY, 150)).toBeNull()
  })

  it('清理后读不到', () => {
    writeAssessmentDetailCache([item(11)])
    clearAssessmentDetailCache()
    expect(readCachedAssessmentItem(CACHE_KEY, 11)).toBeNull()
  })
})

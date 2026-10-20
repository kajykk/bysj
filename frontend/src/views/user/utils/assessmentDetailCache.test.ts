/**
 * 详情页 sessionStorage 快照单测（FIX-2026-10-08；M25 修复 ROUND_23）。
 *
 * 这个模块是「新标签页打开详情链接」的兜底路径，全部行为都必须在
 * 隐私模式（sessionStorage 不可用）、JSON 损坏、配额超限等异常下
 * **静默降级** —— 主路径（history.state）不受影响才是它的设计目的。
 *
 * M25 修复后新增的一整类用例：跨用户隔离。原实现固定键无用户后缀，
 * 同一标签页 A 登出、B 登录后 B 会读到 A 的评估快照（心理健康 PII）。
 * 现在存储键带用户后缀、快照带归属元数据、读取双重校验、取不到
 * 用户 id 一律 fail-closed。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { DataHistoryItem } from '@/api/userTypes'
import {
  CACHE_KEY,
  assessmentDetailCacheKey,
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

/** 用户 A / B 的存储键（键后缀隔离的实证对象）。 */
const keyA = () => assessmentDetailCacheKey(7)
const keyB = () => assessmentDetailCacheKey(8)

describe('assessmentDetailCache —— 详情页快照', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
  })

  it('写入后能按 id 取回', () => {
    writeAssessmentDetailCache([item(11), item(12)], 7)
    expect(readCachedAssessmentItem(7, 12)?.id).toBe(12)
  })

  it('空列表写入会清掉旧快照（切页/筛选后不该残留上一页）', () => {
    writeAssessmentDetailCache([item(11)], 7)
    writeAssessmentDetailCache([], 7)
    expect(readCachedAssessmentItem(7, 11)).toBeNull()
  })

  it('快照里没有该 id 时返回 null，不拿邻近记录顶替', () => {
    writeAssessmentDetailCache([item(12)], 7)
    expect(readCachedAssessmentItem(7, 11)).toBeNull()
  })

  it('JSON 损坏时不抛异常，降级为无快照', () => {
    window.sessionStorage.setItem(keyA()!, '{not json')
    expect(() => readCachedAssessmentItem(7, 11)).not.toThrow()
    expect(readCachedAssessmentItem(7, 11)).toBeNull()
  })

  it('快照不是包裹对象时不抛异常', () => {
    window.sessionStorage.setItem(keyA()!, '{"id":11}')
    expect(readCachedAssessmentItem(7, 11)).toBeNull()
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
    expect(() => writeAssessmentDetailCache([item(11)], 7)).not.toThrow()
    vi.unstubAllGlobals()
  })

  it('sessionStorage 整体不可用时读写都不炸（隐私模式）', () => {
    const boom = () => {
      throw new Error('SecurityError')
    }
    vi.stubGlobal('sessionStorage', { getItem: boom, setItem: boom, removeItem: boom })
    expect(() => writeAssessmentDetailCache([item(11)], 7)).not.toThrow()
    expect(readCachedAssessmentItem(7, 11)).toBeNull()
    expect(() => clearAssessmentDetailCache(7)).not.toThrow()
    vi.unstubAllGlobals()
  })

  it('超过上限时截断而不是把 sessionStorage 撑爆', () => {
    const items = Array.from({ length: 150 }, (_, i) => item(i + 1))
    writeAssessmentDetailCache(items, 7)
    const raw = window.sessionStorage.getItem(keyA()!)
    expect(raw).toBeTruthy()
    const parsed = JSON.parse(raw!) as { items: unknown[] }
    expect(parsed.items.length).toBeLessThanOrEqual(100)
    expect(readCachedAssessmentItem(7, 150)).toBeNull()
  })

  it('清理后读不到', () => {
    writeAssessmentDetailCache([item(11)], 7)
    clearAssessmentDetailCache(7)
    expect(readCachedAssessmentItem(7, 11)).toBeNull()
  })

  // ---- M25 修复（ROUND_23）：跨用户隔离 ----

  it('存储键带用户后缀，与另三个历史键同构', () => {
    expect(keyA()).toBe(`${CACHE_KEY}_u7`)
    expect(keyB()).toBe(`${CACHE_KEY}_u8`)
  })

  it('A 写入 ⇒ 同标签页换 B 登录 ⇒ B 读不到 A 的条目（键后缀隔离）', () => {
    writeAssessmentDetailCache([item(11), item(12)], 7)
    expect(readCachedAssessmentItem(8, 11)).toBeNull()
    expect(readCachedAssessmentItem(8, 12)).toBeNull()
    // A 自己的读取不受影响
    expect(readCachedAssessmentItem(7, 11)?.id).toBe(11)
  })

  it('B 登录后 A 的键仍物理存在（由登出清理负责，不依赖读者自觉）', () => {
    writeAssessmentDetailCache([item(11)], 7)
    // 换用户后 A 的键不会被 B 的读取顺手删掉——清理是登出路径的职责
    readCachedAssessmentItem(8, 11)
    expect(window.sessionStorage.getItem(keyA()!)).not.toBeNull()
  })

  it('归属元数据不符即丢弃（纵深：键后缀对但 userId 被改过）', () => {
    writeAssessmentDetailCache([item(11)], 7)
    const raw = window.sessionStorage.getItem(keyA()!)!
    const snapshot = JSON.parse(raw) as { v: number; userId: number }
    // 篡改归属：键还是 A 的键，但快照里写着 B
    window.sessionStorage.setItem(
      keyA()!,
      JSON.stringify({ ...snapshot, userId: 8 })
    )
    expect(readCachedAssessmentItem(7, 11)).toBeNull()
  })

  it('旧格式（v1 裸数组）按无归属丢弃，并顺手清掉', () => {
    window.sessionStorage.setItem(keyA()!, JSON.stringify([item(11)]))
    expect(readCachedAssessmentItem(7, 11)).toBeNull()
    expect(window.sessionStorage.getItem(keyA()!)).toBeNull()
  })

  it('取不到用户 id 时不写入（fail-closed，不回落匿名键）', () => {
    writeAssessmentDetailCache([item(11)], null)
    writeAssessmentDetailCache([item(11)], undefined)
    writeAssessmentDetailCache([item(11)], 0)
    writeAssessmentDetailCache([item(11)], -1)
    writeAssessmentDetailCache([item(11)], 1.5)
    // 任何键都不该出现——既没有 _u 键，也不该有 anon_ 键
    for (let i = 0; i < window.sessionStorage.length; i++) {
      const key = window.sessionStorage.key(i)!
      expect(key.startsWith(CACHE_KEY)).toBe(false)
    }
  })

  it('取不到用户 id 时读取返回 null（绝不返回上一用户数据）', () => {
    writeAssessmentDetailCache([item(11)], 7)
    expect(readCachedAssessmentItem(null, 11)).toBeNull()
    expect(readCachedAssessmentItem(undefined, 11)).toBeNull()
    // A 的快照原样还在，只是不返回
    expect(window.sessionStorage.getItem(keyA()!)).not.toBeNull()
  })
})

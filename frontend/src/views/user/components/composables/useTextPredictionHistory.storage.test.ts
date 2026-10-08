/**
 * 敏感健康数据的存储位置闸门 (SEC-FIX-2026-10-09).
 *
 * 文本预测历史含用户心理自述片段（content_preview，前 60 字 × 最多 20 条），
 * 属敏感健康信息。原实现写 localStorage，只有"登出/登录"时才被清理 ——
 * 而多数用户直接关闭浏览器而不登出，数据长期明文落盘，共享设备上下一位
 * 打开浏览器即可读取上一位用户的心理自述。
 *
 * 本闸门锁定：读写一律走 sessionStorage，localStorage 不得再出现这些 key。
 * 与 usePredictionHistory / PhysioTab 同口径迁移。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

// 只覆盖 useI18n，保留 vue-i18n 其余导出：
// 直接整体 mock 会让 src/i18n/index.ts 拿不到 createI18n（经 exportUtils 间接引入），
// 在收集期就报错。
vi.mock('vue-i18n', async importOriginal => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return {
    ...actual,
    useI18n: () => ({ t: (key: string) => key }),
  }
})

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
}))

import {
  useTextPredictionHistory,
  type TextPredictionHistoryItem,
} from './useTextPredictionHistory'

const KEY = 'text_prediction_history_v1_u1'

function makeItem(): TextPredictionHistoryItem {
  return {
    prediction: 1,
    probability: 0.72,
    time: '2026-10-09 03:00:00',
    content_preview: '最近压力很大，晚上睡不着',
    source: 'model',
    sentiment_score: -0.3,
    sentiment_label: 'negative',
    model_used: 'text_analyze',
  } as TextPredictionHistoryItem
}

describe('useTextPredictionHistory — 存储位置闸门', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('写入只落 sessionStorage，localStorage 保持为空', () => {
    const { unshift } = useTextPredictionHistory(KEY)
    unshift(makeItem())

    expect(sessionStorage.getItem(KEY)).not.toBeNull()
    expect(localStorage.getItem(KEY)).toBeNull()
    expect(localStorage.length).toBe(0)
  })

  it('load 不读回 localStorage 里的迁移前遗留数据', () => {
    // 老用户浏览器里可能仍有迁移前写入的明文历史；迁移后不应再被读回，
    // 否则"关闭标签页即清除"的承诺会被旧数据绕过。
    localStorage.setItem(KEY, JSON.stringify([makeItem()]))

    const { load, textPredictionHistory } = useTextPredictionHistory(KEY)
    load()

    expect(textPredictionHistory.value.length).toBe(0)
  })

  it('load 正常读回 sessionStorage 中的数据', () => {
    const writer = useTextPredictionHistory(KEY)
    writer.unshift(makeItem())

    const reader = useTextPredictionHistory(KEY)
    reader.load()

    expect(reader.textPredictionHistory.value.length).toBe(1)
    expect(reader.textPredictionHistory.value[0].content_preview).toBe('最近压力很大，晚上睡不着')
  })

  it('clear 清除 sessionStorage 且不产生 localStorage 残留', () => {
    const { unshift, clear } = useTextPredictionHistory(KEY)
    unshift(makeItem())
    clear()

    expect(sessionStorage.getItem(KEY)).toBeNull()
    expect(localStorage.length).toBe(0)
  })
})

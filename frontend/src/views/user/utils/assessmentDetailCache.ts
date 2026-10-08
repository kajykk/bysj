/**
 * 评估详情页的 sessionStorage 快照（FIX-2026-10-08）。
 *
 * 为什么需要它: 详情页改成前端本地渲染后，载荷有两个来源 ——
 *   1. `history.state`：列表 `router.push` 时随路由带过来，刷新/前进/后退都还在；
 *   2. 本模块的 sessionStorage 快照：覆盖「**新标签页**打开同一个详情链接」
 *      和「链接被收藏后重新打开」这两种 history.state 拿不到的情况。
 *
 * 为什么存整页而不是只存被点开的那一条: 详情页按 id 反查，
 * 存整页才能覆盖「先看第 3 页的某条 → 又在新标签打开第 1 页某条」。
 * 单页默认 10-20 条，体积可控。
 *
 * 安全口径: 快照存的是用户自己刚拉到的评估数据，生命周期与会话相同，
 * 退出登录时随之丢弃（见 clearAssessmentDetailCache）；不跨会话保留。
 * 任何读取失败（隐私模式禁写、JSON 损坏、容量超限）都必须静默降级为
 * 「无快照」，绝不把异常抛给渲染层。
 */

import type { DataHistoryItem } from '@/api/userTypes'

export const CACHE_KEY = 'bysj:assessment-history-snapshot'

/**
 * 把列表项编码成可放进 `history.state` 的字符串。
 *
 * 两个必要性：
 * 1. 类型: vue-router 的 `HistoryStateValue` 只接受 string/number/boolean/null/
 *    undefined/嵌套数组对象，而 `DataHistoryItem.data` 是 `Record<string, unknown>`
 *    —— unknown 过宽，直接塞会 TS2345。
 * 2. 运行时: `rawItems` 是 ref，取出来的对象是 Vue **响应式代理**；
 *    放进 history.state 会让这个代理随浏览器历史条目长期存活
 *    （前进/后退/刷新都能碰到），既容易泄漏也存在代理语义差异。
 *    序列化一次顺便剥离代理，只留纯数据。
 */
export function encodeStatePayload(item: DataHistoryItem | null): string {
  if (!item) return ''
  try {
    return JSON.stringify(item)
  } catch {
    return ''
  }
}

/** `encodeStatePayload` 的逆操作。任何非法输入都返回 null，由调用方 fail-closed。 */
export function decodeStatePayload(raw: unknown): DataHistoryItem | null {
  if (typeof raw !== 'string' || raw === '') return null
  try {
    const parsed: unknown = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? (parsed as DataHistoryItem) : null
  } catch {
    return null
  }
}

/** 超过这个条数就不再写入：防止 page_size 被调成极大值时撑爆 sessionStorage 配额。 */
const MAX_CACHED_ITEMS = 100

function storage(): Storage | null {
  try {
    // 隐私模式 / 禁用存储时访问 sessionStorage 本身就可能抛异常。
    return typeof window !== 'undefined' && window.sessionStorage ? window.sessionStorage : null
  } catch {
    return null
  }
}

/** 写入当前页快照。任何失败都静默忽略（快照只是兜底，不是主路径）。 */
export function writeAssessmentDetailCache(items: DataHistoryItem[] | null | undefined): void {
  const store = storage()
  if (!store) return
  try {
    if (!items || items.length === 0) {
      store.removeItem(CACHE_KEY)
      return
    }
    store.setItem(CACHE_KEY, JSON.stringify(items.slice(0, MAX_CACHED_ITEMS)))
  } catch {
    /* 配额超限等：详情页会回落到 history.state 或提示回列表，不影响主流程 */
  }
}

/** 按 id 读取快照项。 */
export function readCachedAssessmentItem(key: string, id: number): DataHistoryItem | null {
  const store = storage()
  if (!store) return null
  try {
    const raw = store.getItem(key)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return null
    const hit = parsed.find(entry => Number((entry as DataHistoryItem)?.id) === id)
    return hit && typeof hit === 'object' ? (hit as DataHistoryItem) : null
  } catch {
    return null
  }
}

export function clearAssessmentDetailCache(key: string = CACHE_KEY): void {
  const store = storage()
  if (!store) return
  try {
    store.removeItem(key)
  } catch {
    /* 同上，清理失败无需打扰用户 */
  }
}

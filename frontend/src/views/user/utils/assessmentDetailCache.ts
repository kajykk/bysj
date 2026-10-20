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
 * M25 修复（ROUND_23，跨用户泄漏）：
 *   原实现用固定键 `bysj:assessment-history-snapshot`（无用户后缀）——
 *   同一标签页内 A 登出、B 登录后，B 打开详情页会读到 A 的评估快照
 *   （心理健康数据，共享设备场景即 PII 泄漏）；且 `clearAssessmentDetailCache`
 *   没有任何生产调用点，docstring 里「退出登录时随之丢弃」是句空话。
 *   修复采取「键后缀 + 读取归属校验」双重防线（单一手段不足以自证）：
 *     1. 存储键加用户后缀，与另三个历史键同构
 *        （`<base>_u<userId>`，见 utils/sensitiveStorage 的
 *        `historyKeyWithUser`）；
 *     2. 快照包裹 `{v, userId, items}` 元数据，读取时校验归属，
 *        不符即丢弃（纵深：防键计算用了过期 userId 等边缘路径）；
 *     3. 取不到当前用户 id 时 **fail-closed**：不写入、不读取——
 *        评估详情只可能属于登录用户，绝不回落到匿名键或他人数据；
 *     4. 登出清理改走 `clearSensitiveLocalStorage`：本键已纳入
 *        SENSITIVE_KEY_PATTERNS，登出/登录时统一清除两种 storage
 *        （原「退出登录时随之丢弃」的承诺由此真正成立）；
 *     5. 旧格式（v1 裸数组，无归属信息）一律按无归属丢弃——
 *        sessionStorage 生命周期本就跟会话同长，一次性升级成本可忽略。
 *
 * 任何读取失败（隐私模式禁写、JSON 损坏、容量超限）都必须静默降级为
 * 「无快照」，绝不把异常抛给渲染层。
 */

import type { DataHistoryItem } from '@/api/userTypes'
import { historyKeyWithUser } from '@/utils/sensitiveStorage'

export const CACHE_KEY = 'bysj:assessment-history-snapshot'

/** 快照包裹格式版本。v1 = 修复前的裸数组（无归属信息，读取时丢弃）。 */
const SNAPSHOT_VERSION = 2

interface AssessmentSnapshotV2 {
  v: number
  userId: number
  items: DataHistoryItem[]
}

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

/**
 * 当前用户的快照存储键；取不到有效 userId 时返回 null（fail-closed）。
 *
 * 与 `historyKeyWithUser` 的刻意差异：后者对缺失 userId 回落到
 * `anon_` 会话键（三个历史键的匿名隔离语义）；本模块**不回落**——
 * 评估详情是登录后才拉得到的数据，无 userId 时不落盘，从源头消除
 * 「匿名会话写入的键被后续登录者复用」的可能。
 */
export function assessmentDetailCacheKey(
  userId: number | null | undefined
): string | null {
  if (typeof userId !== 'number' || !Number.isInteger(userId) || userId <= 0) {
    return null
  }
  return historyKeyWithUser(CACHE_KEY, userId)
}

/**
 * 写入当前用户的整页快照。任何失败都静默忽略（快照只是兜底，不是主路径）。
 *
 * userId 无效时不写入（fail-closed）：宁可让详情页走「提示回列表」的
 * 明路径，也不把无归属的数据留在存储里。
 */
export function writeAssessmentDetailCache(
  items: DataHistoryItem[] | null | undefined,
  userId: number | null | undefined
): void {
  const store = storage()
  if (!store) return
  const key = assessmentDetailCacheKey(userId)
  if (!key) return
  try {
    if (!items || items.length === 0) {
      store.removeItem(key)
      return
    }
    const snapshot: AssessmentSnapshotV2 = {
      v: SNAPSHOT_VERSION,
      userId: Number(userId),
      items: items.slice(0, MAX_CACHED_ITEMS),
    }
    store.setItem(key, JSON.stringify(snapshot))
  } catch {
    /* 配额超限等：详情页会回落到 history.state 或提示回列表，不影响主流程 */
  }
}

/**
 * 按 id 读取**当前用户**的快照项。
 *
 * 三重校验，任一不过即返回 null（fail-closed）：
 *   1. userId 有效（否则不计算键、不读取）；
 *   2. 快照包裹格式版本与归属 userId 匹配（v1 裸数组 / 他人快照一律丢弃）；
 *   3. 条目 id 命中。
 */
export function readCachedAssessmentItem(
  userId: number | null | undefined,
  id: number
): DataHistoryItem | null {
  const store = storage()
  if (!store) return null
  const key = assessmentDetailCacheKey(userId)
  if (!key) return null
  try {
    const raw = store.getItem(key)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    const snapshot = parsed as Partial<AssessmentSnapshotV2>
    // 归属校验：版本、userId、items 三样缺一即视为不可信快照。
    if (
      snapshot.v !== SNAPSHOT_VERSION ||
      snapshot.userId !== userId ||
      !Array.isArray(snapshot.items)
    ) {
      store.removeItem(key)
      return null
    }
    const hit = snapshot.items.find(entry => Number(entry?.id) === id)
    return hit && typeof hit === 'object' ? (hit as DataHistoryItem) : null
  } catch {
    return null
  }
}

/**
 * 显式清除指定用户的快照（详情页主动离开、测试隔离等场景）。
 *
 * 登出清理不经过此函数——见 docstring 第 4 条：登出时用户态已清空，
 * 拿不到 userId，统一由 `clearSensitiveLocalStorage` 按 SENSITIVE_KEY_PATTERNS
 * 模式清除（两种 storage 都清）。
 */
export function clearAssessmentDetailCache(
  userId: number | null | undefined
): void {
  const store = storage()
  if (!store) return
  const key = assessmentDetailCacheKey(userId)
  if (!key) return
  try {
    store.removeItem(key)
  } catch {
    /* 清理失败无需打扰用户 */
  }
}

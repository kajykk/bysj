/**
 * P1-28 修复：localStorage 安全读写。
 *
 * 问题：`stores/layout.ts` 在 store 初始化时直接 `localStorage.getItem(...)`。
 * 存储不可用时（Safari 隐私模式、用户禁用站点数据、配额已满、企业策略禁止）
 * `getItem`/`setItem` 会**抛异常**——而这是在 Pinia store 创建阶段，
 * 异常直接冒到应用挂载链上 → 整站白屏，用户连错误提示都看不到。
 *
 * 本仓其实已有正确范式：`utils/authStorage.ts` 的 `_safeGetItem/_safeSetItem`
 * （ISS-008）与 `utils/sensitiveStorage.ts` 的 try/catch。但它是模块私有的，
 * 于是每个新用到 localStorage 的地方都各自裸调 —— 正是报告 P2-32
 * 「同一模式复制 N 份后各自漂移」的又一实例。
 *
 * 本模块抽成唯一入口，新增存储用法一律走这里。
 * 刻意不做「改成内存 Map 兜底」：UI 偏好丢失可接受，静默改变语义不可接受。
 */

const TEST_KEY = '__safe_storage_test__'

function _isAvailable(storage: Storage): boolean {
  try {
    storage.setItem(TEST_KEY, '1')
    storage.removeItem(TEST_KEY)
    return true
  } catch {
    return false
  }
}

let _available: boolean | null = null

/** 存储是否可用（每次调用都重新探测，避免用户中途切换隐私模式后状态过期）。 */
export function isLocalStorageAvailable(): boolean {
  if (typeof window === 'undefined') return false
  _available = _isAvailable(window.localStorage)
  return _available
}

/** 安全读取；不可用或抛错时返回 null（调用方按「无偏好」处理）。 */
export function safeLocalGetItem(key: string): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

/** 安全写入；不可用或抛错时静默失败（UI 偏好丢失优于白屏）。 */
export function safeLocalSetItem(key: string, value: string): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // 配额已满 / 隐私模式：忽略。侧边栏折叠态不值得为它阻断整个应用。
  }
}

/** 安全删除。 */
export function safeLocalRemoveItem(key: string): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(key)
  } catch {
    // 同上
  }
}

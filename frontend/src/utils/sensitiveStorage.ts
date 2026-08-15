/**
 * SEC-FIX (H4): 登出时清理 localStorage 中的敏感健康数据
 *
 * 多个页面把用户级敏感数据 (日记预览/生理记录/结构化评估历史) 明文写入
 * localStorage, 且从未在登出时清理——同浏览器后续登录者 (含共享设备场景)
 * 可读取上一用户数据, 违反 PII 最小化原则。
 *
 * 这些 key 由 `historyKeyWithUser()` 统一生成:
 *   - 登录用户: `<base>_u<userId>`
 *   - 匿名会话: `<base>_anon_<会话随机ID>` (sessionStorage 级隔离)
 * 本工具在登出/登录时统一清除, 不依赖具体页面加载。
 */

const SENSITIVE_KEY_PATTERNS: RegExp[] = [
  // 日记文本预测历史 (TextAssessTab)
  /^text_prediction_history_v1_(u\d+|anon_.+)$/,
  // 生理记录历史 (PhysioTab)
  /^physio_history_v1_(u\d+|anon_.+)$/,
  // 结构化评估预测历史 (usePredictionHistory)
  /^prediction_history_v1_(u\d+|anon_.+)$/,
]

let cachedAnonSessionId: string | null = null

/**
 * 匿名会话 ID (sessionStorage 级随机串).
 *
 * SEC-FIX (H4 补强): 匿名场景下各页面生成的 `<base>_u0` key 在同一设备上
 * 被所有匿名用户共享 (互相覆盖/可读); 统一改为会话级随机 ID 隔离,
 * 并由 clearSensitiveLocalStorage 的 `_anon_.+` 模式统一清理。
 */
function getAnonSessionId(): string {
  if (cachedAnonSessionId) return cachedAnonSessionId
  const key = 'sensitive_anon_session_id'
  try {
    let id = sessionStorage.getItem(key)
    if (!id) {
      id = 'anon_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
      sessionStorage.setItem(key, id)
    }
    cachedAnonSessionId = id
  } catch {
    // sessionStorage 不可用 (隐私模式) 时回退到内存随机 ID
    cachedAnonSessionId =
      'anon_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
  }
  return cachedAnonSessionId
}

/**
 * 生成敏感数据存储 key: 登录用户按 userId 隔离, 匿名用户按会话隔离.
 */
export function historyKeyWithUser(
  base: string,
  userId: number | null | undefined
): string {
  if (userId && userId > 0) return `${base}_u${userId}`
  return `${base}_anon_${getAnonSessionId()}`
}

export function clearSensitiveLocalStorage(): void {
  if (typeof window === 'undefined' || !window.localStorage) return
  try {
    const keysToRemove: string[] = []
    for (let i = 0; i < window.localStorage.length; i++) {
      const key = window.localStorage.key(i)
      if (!key) continue
      if (SENSITIVE_KEY_PATTERNS.some((pattern) => pattern.test(key))) {
        keysToRemove.push(key)
      }
    }
    for (const key of keysToRemove) {
      window.localStorage.removeItem(key)
    }
  } catch {
    // localStorage 不可用 (隐私模式/配额) 时静默降级
  }
}

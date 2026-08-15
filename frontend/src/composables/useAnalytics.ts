/**
 * P1-5 埋点与隐私闭环：最小化事件模型 + 同意/撤回机制
 *
 * 事件模型遵循"最小化"原则：
 * - 仅采集事件类型、时间戳和分类元数据（如 assessment_type、risk_level）
 * - 禁止采集问卷正文、敏感健康原文、用户输入文本
 * - 用户可随时同意/撤回
 *
 * 使用方式：
 *   const { track } = useAnalytics()
 *   track('assessment_start', { assessment_type: 'structured' })
 */

import { ref, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

// ===== 事件类型白名单 =====
export type AnalyticsEventType =
  | 'assessment_enter'
  | 'assessment_start'
  | 'assessment_complete'
  | 'assessment_abandon'
  | 'warning_handle'
  | 'help_use'
  | 'task_fail'

// 允许的元数据键（与后端白名单一致）
export interface AnalyticsMetadata {
  assessment_type?: 'structured' | 'text' | 'physiological' | 'fusion'
  risk_level?: number
  warning_id?: number
  help_action?: 'faq' | 'contact' | 'feedback' | 'onboarding'
  task_type?: 'export' | 'training' | 'report'
  error_code?: string
  page?: string
}

// 同意状态缓存（进程级，避免每次 track 都请求后端）
let _consented: boolean | null = null
let _consentLoading: Promise<boolean> | null = null

const ANALYTICS_ENDPOINT = '/api/v1/analytics/events'
const CONSENT_ENDPOINT = '/api/v1/analytics/consent'

/**
 * 从后端加载同意状态（带缓存，避免重复请求）
 */
async function loadConsent(): Promise<boolean> {
  if (_consented !== null) return _consented
  if (_consentLoading) return _consentLoading

  _consentLoading = (async () => {
    try {
      const token = useAuthStore().token
      if (!token) {
        _consented = false
        return false
      }
      const resp = await fetch(CONSENT_ENDPOINT, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!resp.ok) {
        _consented = false
        return false
      }
      const data = await resp.json()
      // 后端返回 { code: 0, data: { consented: bool, ... } }
      _consented = Boolean(data?.data?.consented ?? data?.consented ?? false)
      return _consented
    } catch {
      _consented = false
      return false
    } finally {
      _consentLoading = null
    }
  })()

  return _consentLoading
}

/**
 * 更新同意状态（同意/撤回），同时刷新本地缓存
 */
async function updateConsent(consent: boolean): Promise<boolean> {
  const token = useAuthStore().token
  if (!token) throw new Error('未登录')

  const resp = await fetch(CONSENT_ENDPOINT, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ consent }),
  })

  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}))
    throw new Error(detail?.detail || '更新同意状态失败')
  }

  _consented = consent
  return consent
}

/**
 * 发送事件到后端
 *
 * SEC-FIX: 原实现无条件优先 sendBeacon —— 但 sendBeacon 无法携带 Authorization 头，
 * 所有事件实际都以未认证请求到达后端（要么被拒导致埋点失效，要么成为未认证写入通道）。
 * 现改为始终使用带 Bearer token 的 fetch；keepalive: true 可保证页面卸载时仍能发送。
 */
function sendEvents(events: Array<{ event_type: string; timestamp: number; metadata: Record<string, unknown> }>): void {
  const token = useAuthStore().token
  if (!token) return

  const payload = JSON.stringify({ events })

  fetch(ANALYTICS_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: payload,
    keepalive: true,
  }).catch(() => {
    // 静默失败，不影响用户操作
  })
}

/**
 * 分析事件追踪 composable
 *
 * 返回:
 * - track: 追踪事件（自动检查同意状态，未同意时静默跳过）
 * - consented: 当前同意状态（响应式 ref）
 * - refreshConsent: 重新从后端加载同意状态
 * - setConsent: 更新同意状态
 */
export function useAnalytics() {
  const consented: Ref<boolean> = ref(false)

  const refreshConsent = async () => {
    consented.value = await loadConsent()
    return consented.value
  }

  const setConsent = async (consent: boolean) => {
    await updateConsent(consent)
    consented.value = consent
  }

  const track = async (eventType: AnalyticsEventType, metadata: AnalyticsMetadata = {}) => {
    // 检查同意状态（首次调用时从后端加载）
    if (_consented === null) {
      await loadConsent()
    }
    if (!_consented) return // 未同意时静默跳过

    // 清理元数据：移除 undefined 值，确保 page 字段不含 query string
    const cleanMeta: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(metadata)) {
      if (value !== undefined) {
        cleanMeta[key] = value
      }
    }

    const event = {
      event_type: eventType,
      timestamp: Date.now(),
      metadata: cleanMeta,
    }

    sendEvents([event])
  }

  return {
    track,
    consented,
    refreshConsent,
    setConsent,
  }
}

/**
 * SEC-FIX (C3/M7): 登出时重置模块级同意缓存，
 * 避免 A 用户的同意状态在同标签页内被 B 用户继承。
 */
export function resetAnalyticsConsent() {
  _consented = null
  _consentLoading = null
}

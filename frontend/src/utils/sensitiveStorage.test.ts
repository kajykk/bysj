import { beforeEach, describe, expect, it } from 'vitest'
import { clearSensitiveLocalStorage } from './sensitiveStorage'

describe('sensitiveStorage - SEC-FIX (H4)', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('登出时同时清理 sessionStorage 内的敏感历史 key', () => {
    // SEC-FIX-2026-10-09: 三处历史已迁到 sessionStorage（关闭标签页即清除）。
    // 若登出只清 localStorage，"登出即清"这条防线在迁移后会失效。
    sessionStorage.setItem('text_prediction_history_v1_u1', '{"content_preview":"diary"}')
    sessionStorage.setItem('physio_history_v1_u1', '{"heart_rate":72}')
    sessionStorage.setItem('prediction_history_v1_u1', '[{"risk_level":2}]')

    clearSensitiveLocalStorage()

    expect(sessionStorage.getItem('text_prediction_history_v1_u1')).toBeNull()
    expect(sessionStorage.getItem('physio_history_v1_u1')).toBeNull()
    expect(sessionStorage.getItem('prediction_history_v1_u1')).toBeNull()
  })

  it('不影响 sessionStorage 里的非敏感 key', () => {
    // 匿名会话 ID 与 access token 不在敏感历史模式内，登出/清理不应误伤
    sessionStorage.setItem('sensitive_anon_session_id', 'anon_123_abc')
    sessionStorage.setItem('token', 'access-token-should-survive-this-call')

    clearSensitiveLocalStorage()

    expect(sessionStorage.getItem('sensitive_anon_session_id')).toBe('anon_123_abc')
    expect(sessionStorage.getItem('token')).toBe('access-token-should-survive-this-call')
  })

  it('清除用户级敏感历史 key', () => {
    localStorage.setItem('text_prediction_history_v1_u1', '{"content_preview":"diary"}')
    localStorage.setItem('physio_history_v1_u1', '{"heart_rate":72}')
    localStorage.setItem('prediction_history_v1_u1', '[{"risk_level":2}]')

    clearSensitiveLocalStorage()

    expect(localStorage.getItem('text_prediction_history_v1_u1')).toBeNull()
    expect(localStorage.getItem('physio_history_v1_u1')).toBeNull()
    expect(localStorage.getItem('prediction_history_v1_u1')).toBeNull()
  })

  it('覆盖任意用户 id 的历史 key', () => {
    localStorage.setItem('text_prediction_history_v1_u42', 'x')
    clearSensitiveLocalStorage()
    expect(localStorage.getItem('text_prediction_history_v1_u42')).toBeNull()
  })

  it('不影响非敏感 key (locale/theme/remember username)', () => {
    localStorage.setItem('locale', 'zh-CN')
    localStorage.setItem('theme', 'dark')
    localStorage.setItem('dws_remember_username', 'alice')
    localStorage.setItem('sidebar_collapsed', 'false')

    clearSensitiveLocalStorage()

    expect(localStorage.getItem('locale')).toBe('zh-CN')
    expect(localStorage.getItem('theme')).toBe('dark')
    expect(localStorage.getItem('dws_remember_username')).toBe('alice')
    expect(localStorage.getItem('sidebar_collapsed')).toBe('false')
  })
})

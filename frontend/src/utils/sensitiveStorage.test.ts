import { beforeEach, describe, expect, it } from 'vitest'
import { clearSensitiveLocalStorage } from './sensitiveStorage'

describe('sensitiveStorage - SEC-FIX (H4)', () => {
  beforeEach(() => {
    localStorage.clear()
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

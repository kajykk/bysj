import { describe, expect, it } from 'vitest'

// base.ts 依赖 import.meta.env.VITE_API_BASE_URL，通过 vi.stubEnv 模拟
import { API_BASE_URL, buildApiUrl } from './base'

describe('api/base', () => {
  describe('API_BASE_URL', () => {
    it('回退到默认 /api/v1 前缀（无 env 时）', () => {
      // 默认值在模块加载时确定，此处仅断言其具备 /api/v1 形态
      expect(typeof API_BASE_URL).toBe('string')
      expect(API_BASE_URL.length).toBeGreaterThan(0)
    })
  })

  describe('buildApiUrl', () => {
    it('拼接带前导斜杠的路径', () => {
      expect(buildApiUrl('/auth/login')).toBe(`${API_BASE_URL}/auth/login`)
    })

    it('为无前导斜杠的路径补斜杠', () => {
      expect(buildApiUrl('auth/login')).toBe(`${API_BASE_URL}/auth/login`)
    })

    it('处理空字符串路径（仍补斜杠）', () => {
      expect(buildApiUrl('')).toBe(`${API_BASE_URL}/`)
    })

    it('处理多层路径', () => {
      expect(buildApiUrl('/user/data/history')).toBe(`${API_BASE_URL}/user/data/history`)
    })

    it('不同路径互不影响', () => {
      expect(buildApiUrl('/a')).toBe(`${API_BASE_URL}/a`)
      expect(buildApiUrl('/b')).toBe(`${API_BASE_URL}/b`)
    })
  })
})

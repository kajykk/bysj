import { beforeEach, describe, expect, it, vi } from 'vitest'

// 模拟 request 模块以隔离测试 userBindingApi
vi.mock('./request', () => ({
  default: {
    get: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config })),
    post: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
    put: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
    delete: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config }))
  },
  requestData: vi.fn(async (promise: Promise<{ data: unknown }>) => {
    const response = await promise
    return response.data
  }),
  requestPageData: vi.fn(async (promise: Promise<{ data: unknown }>) => {
    const response = await promise
    return response.data
  })
}))

import request, { requestData } from './request'
import { userBindingApi } from './userBindingApi'

describe('api/userBindingApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getUserBinding', () => {
    it('调用 GET /user/data/binding 解包绑定信息', async () => {
      const binding = {
        binding_id: 1,
        counselor_id: 2,
        counselor_name: 'Dr. Bob',
        counselor_email: 'b@e.com',
        bound_at: '2026-01-01T00:00:00Z',
        status: 'active',
        bind_code_status: 'active'
      }
      ;(requestData as any).mockResolvedValueOnce(binding)
      const res = await userBindingApi.getUserBinding()
      expect(request.get).toHaveBeenCalledWith('/user/data/binding')
      expect(res).toEqual(binding)
    })

    it('未绑定时返回 null', async () => {
      (requestData as any).mockResolvedValueOnce(null)
      const res = await userBindingApi.getUserBinding()
      expect(res).toBeNull()
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('401'))
      await expect(userBindingApi.getUserBinding()).rejects.toThrow('401')
    })
  })

  describe('bindCounselor', () => {
    it('通过 POST /user/data/binding 绑定 counselor', async () => {
      const result = {
        binding_id: 5,
        counselor_id: 9,
        counselor_name: 'Dr. Bob',
        counselor_email: 'b@e.com',
        bound_at: '2026-06-29T00:00:00Z',
        status: 'active',
        bind_code_status: 'active'
      }
      ;(requestData as any).mockResolvedValueOnce(result)
      const res = await userBindingApi.bindCounselor('ABC123')

      expect(request.post).toHaveBeenCalledWith('/user/data/binding', { bind_code: 'ABC123' })
      expect(res).toEqual(result)
    })

    it('bind_code 无效时透传错误', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('410'))
      await expect(userBindingApi.bindCounselor('BAD')).rejects.toThrow('410')
    })

    it('边界：空字符串 bind_code', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userBindingApi.bindCounselor('')
      expect(request.post).toHaveBeenCalledWith('/user/data/binding', { bind_code: '' })
    })
  })

  describe('unbindCounselor', () => {
    it('通过 DELETE /user/data/binding 解绑', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'unbound' })
      const res = await userBindingApi.unbindCounselor()
      expect(request.delete).toHaveBeenCalledWith('/user/data/binding')
      expect(res).toEqual({ message: 'unbound' })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userBindingApi.unbindCounselor()).rejects.toThrow('500')
    })
  })
})

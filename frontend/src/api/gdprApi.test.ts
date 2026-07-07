import { beforeEach, describe, expect, it, vi } from 'vitest'

// 模拟 request 模块以隔离测试 gdprApi
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
import { gdprApi } from './gdprApi'

describe('api/gdprApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('exportUserData', () => {
    it('调用 GET /user/gdpr/export 并以 blob 形式接收响应', async () => {
      const blob = new Blob(['data'], { type: 'application/zip' })
      ;(request.get as any).mockResolvedValueOnce({ data: blob })
      const res = await gdprApi.exportUserData()

      expect(request.get).toHaveBeenCalledWith('/user/gdpr/export', { responseType: 'blob' })
      expect(res).toEqual({ data: blob })
    })

    it('导出失败时透传错误', async () => {
      (request.get as any).mockRejectedValueOnce(new Error('401'))
      await expect(gdprApi.exportUserData()).rejects.toThrow('401')
    })

    it('服务端返回 500 时透传', async () => {
      (request.get as any).mockRejectedValueOnce(new Error('500'))
      await expect(gdprApi.exportUserData()).rejects.toThrow('500')
    })
  })

  describe('deleteAccount', () => {
    it('通过 POST /user/gdpr/delete 匿名化账户', async () => {
      const expected = {
        user_id: 9,
        anonymized_at: '2026-06-29T00:00:00Z',
        original_email_masked: 'a***@e.com',
        contacts_anonymized: 3,
        sessions_revoked: 5,
        risk_assessments_deleted: 12,
        legal_records_retained: true,
        warning: 'some records retained'
      }
      ;(requestData as any).mockResolvedValueOnce(expected)
      const res = await gdprApi.deleteAccount({ password: 'pw', confirm: true })

      expect(request.post).toHaveBeenCalledWith('/user/gdpr/delete', { password: 'pw', confirm: true })
      expect(res).toEqual(expected)
    })

    it('confirm=false 时仍按原样传递', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await gdprApi.deleteAccount({ password: 'pw', confirm: false })
      expect(request.post).toHaveBeenCalledWith('/user/gdpr/delete', { password: 'pw', confirm: false })
    })

    it('密码错误时透传 401', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('401'))
      await expect(gdprApi.deleteAccount({ password: 'bad', confirm: true })).rejects.toThrow('401')
    })

    it('服务端异常时透传 500', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(gdprApi.deleteAccount({ password: 'pw', confirm: true })).rejects.toThrow('500')
    })
  })
})

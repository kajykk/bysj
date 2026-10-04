import { beforeEach, describe, expect, it, vi } from 'vitest'

// 模拟 request 模块以隔离测试 userFileApi
vi.mock('./request', () => ({
  default: {
    get: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config })),
    post: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
    put: vi.fn((url: string, data?: unknown, config?: unknown) => Promise.resolve({ url, data, config })),
    delete: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config }))
  },
  dedupedGet: vi.fn((url: string, config?: unknown) => Promise.resolve({ url, config })),
  requestData: vi.fn(async (promise: Promise<{ data: unknown }>) => {
    const response = await promise
    return response.data
  }),
  requestPageData: vi.fn(async (promise: Promise<{ data: unknown }>) => {
    const response = await promise
    return response.data
  })
}))

import request, { dedupedGet, requestData } from './request'
import { userFileApi } from './userFileApi'

describe('api/userFileApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('exportRiskPdf', () => {
    it('默认 days=90 调用 GET /user/risk/export 以 PDF 形式导出', async () => {
      const blob = new Blob(['pdf'], { type: 'application/pdf' })
      ;(dedupedGet as any).mockResolvedValueOnce({ data: blob })
      await userFileApi.exportRiskPdf()
      expect(dedupedGet).toHaveBeenCalledWith('/user/risk/export', {
        params: { format: 'pdf', days: 90 },
        responseType: 'blob'
      })
    })

    it('显式传入 days 覆盖默认值', async () => {
      (dedupedGet as any).mockResolvedValueOnce({ data: new Blob() })
      await userFileApi.exportRiskPdf(30)
      expect(dedupedGet).toHaveBeenCalledWith('/user/risk/export', {
        params: { format: 'pdf', days: 30 },
        responseType: 'blob'
      })
    })

    it('错误透传', async () => {
      (dedupedGet as any).mockRejectedValueOnce(new Error('500'))
      await expect(userFileApi.exportRiskPdf()).rejects.toThrow('500')
    })
  })

  describe('exportRiskData', () => {
    it('format=json 调用 GET /user/risk/export', async () => {
      (dedupedGet as any).mockResolvedValueOnce({ data: { ok: true } })
      await userFileApi.exportRiskData('json', 30)
      expect(dedupedGet).toHaveBeenCalledWith('/user/risk/export', {
        params: { format: 'json', days: 30 },
        responseType: 'blob'
      })
    })

    it('format=csv 默认 days=90', async () => {
      (dedupedGet as any).mockResolvedValueOnce({ data: new Blob() })
      await userFileApi.exportRiskData('csv')
      expect(dedupedGet).toHaveBeenCalledWith('/user/risk/export', {
        params: { format: 'csv', days: 90 },
        responseType: 'blob'
      })
    })

    it('format=pdf 显式 days', async () => {
      (dedupedGet as any).mockResolvedValueOnce({ data: new Blob() })
      await userFileApi.exportRiskData('pdf', 180)
      expect(dedupedGet).toHaveBeenCalledWith('/user/risk/export', {
        params: { format: 'pdf', days: 180 },
        responseType: 'blob'
      })
    })

    it('错误透传', async () => {
      (dedupedGet as any).mockRejectedValueOnce(new Error('401'))
      await expect(userFileApi.exportRiskData('json', 1)).rejects.toThrow('401')
    })
  })

  describe('uploadFile', () => {
    it('携带 category 参数上传文件', async () => {
      const formData = new FormData()
      formData.append('file', new Blob(['x']), 'f.txt')
      const expected = { url: 'http://x/f', filename: 'f', original_name: 'f.txt', size: 1, content_type: 'text/plain' }
      ;(requestData as any).mockResolvedValueOnce(expected)
      const res = await userFileApi.uploadFile(formData, 'avatar')

      expect(request.post).toHaveBeenCalledWith('/user/upload', formData, { params: { category: 'avatar' } })
      expect(res).toEqual(expected)
    })

    it('不传 category 时 params 为空对象', async () => {
      const formData = new FormData()
      ;(requestData as any).mockResolvedValueOnce(undefined)
      await userFileApi.uploadFile(formData)
      expect(request.post).toHaveBeenCalledWith('/user/upload', formData, { params: {} })
    })

    it('显式传 undefined 时 params 为空对象', async () => {
      const formData = new FormData()
      ;(requestData as any).mockResolvedValueOnce(undefined)
      await userFileApi.uploadFile(formData, undefined)
      expect(request.post).toHaveBeenCalledWith('/user/upload', formData, { params: {} })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('413'))
      await expect(userFileApi.uploadFile(new FormData())).rejects.toThrow('413')
    })
  })

  describe('uploadFiles（批量，AUDIT-2026-10-01 决策三 P6）', () => {
    it('通过 POST /user/upload/batch 上传并携带 category', async () => {
      const formData = new FormData()
      formData.append('files', new Blob(['x']), 'a.txt')
      formData.append('files', new Blob(['y']), 'b.txt')
      const expected = {
        items: [
          { url: 'http://x/a', filename: 'a', original_name: 'a.txt', size: 1 },
          { filename: 'b.txt', error: '不支持的文件类型: .txt' }
        ],
        count: 2,
        total: 2,
        failed: 1
      }
      ;(requestData as any).mockResolvedValueOnce(expected)
      const res = await userFileApi.uploadFiles(formData, 'image')

      expect(request.post).toHaveBeenCalledWith('/user/upload/batch', formData, { params: { category: 'image' } })
      expect(res).toEqual(expected)
    })

    it('不传 category 时 params 为空对象', async () => {
      const formData = new FormData()
      ;(requestData as any).mockResolvedValueOnce({ items: [], count: 0 })
      await userFileApi.uploadFiles(formData)
      expect(request.post).toHaveBeenCalledWith('/user/upload/batch', formData, { params: {} })
    })

    it('单文件失败项带 error 字段，调用方需逐项检查', async () => {
      const formData = new FormData()
      ;(requestData as any).mockResolvedValueOnce({
        items: [{ filename: 'bad.exe', error: '不支持的文件类型: .exe' }],
        count: 1
      })
      const res = await userFileApi.uploadFiles(formData)
      expect(res.items?.[0].error).toBeDefined()
      expect(res.items?.[0].url).toBeUndefined()
    })

    it('超过 10 个文件的后端 400 错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('400'))
      await expect(userFileApi.uploadFiles(new FormData())).rejects.toThrow('400')
    })
  })
})

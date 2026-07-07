import { beforeEach, describe, expect, it, vi } from 'vitest'

// 模拟 request 模块以隔离测试 userContentApi
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

import request, { requestData, requestPageData } from './request'
import { userContentApi } from './userContentApi'

describe('api/userContentApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('listContents', () => {
    it('携带完整过滤参数调用 GET /user/content/', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userContentApi.listContents({
        page: 2,
        page_size: 20,
        category: 'stress',
        content_type: 'article',
        keyword: 'sleep'
      })
      expect(request.get).toHaveBeenCalledWith('/user/content/', {
        params: {
          page: 2,
          page_size: 20,
          category: 'stress',
          content_type: 'article',
          keyword: 'sleep'
        }
      })
    })

    it('默认分页 + 全 undefined 过滤', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userContentApi.listContents()
      expect(request.get).toHaveBeenCalledWith('/user/content/', {
        params: {
          page: 1,
          page_size: 10,
          category: undefined,
          content_type: undefined,
          keyword: undefined
        }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userContentApi.listContents()).rejects.toThrow('500')
    })
  })

  describe('getContentDetail', () => {
    it('调用 GET /user/content/:contentId', async () => {
      (requestData as any).mockResolvedValueOnce({ id: 12, title: 't' })
      await userContentApi.getContentDetail(12)
      expect(request.get).toHaveBeenCalledWith('/user/content/12')
    })

    it('contentId=0 时路径仍按规则拼接', async () => {
      (requestData as any).mockResolvedValueOnce(undefined)
      await userContentApi.getContentDetail(0)
      expect(request.get).toHaveBeenCalledWith('/user/content/0')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('404'))
      await expect(userContentApi.getContentDetail(99)).rejects.toThrow('404')
    })
  })

  describe('toggleFavorite', () => {
    it('通过 POST /user/content/:id/favorite 切换收藏', async () => {
      (requestData as any).mockResolvedValueOnce({ message: 'favorited' })
      await userContentApi.toggleFavorite(7)
      expect(request.post).toHaveBeenCalledWith('/user/content/7/favorite')
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('401'))
      await expect(userContentApi.toggleFavorite(1)).rejects.toThrow('401')
    })
  })

  describe('listFavorites', () => {
    it('携带默认分页调用 GET /user/content/favorites/list', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userContentApi.listFavorites()
      expect(request.get).toHaveBeenCalledWith('/user/content/favorites/list', {
        params: { page: 1, page_size: 10 }
      })
    })

    it('携带显式分页', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 3, page_size: 25 })
      await userContentApi.listFavorites({ page: 3, page_size: 25 })
      expect(request.get).toHaveBeenCalledWith('/user/content/favorites/list', {
        params: { page: 3, page_size: 25 }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userContentApi.listFavorites()).rejects.toThrow('500')
    })
  })

  describe('listRecommendations', () => {
    it('调用 GET /user/content/recommendations', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userContentApi.listRecommendations({ page: 1, page_size: 5 })
      expect(request.get).toHaveBeenCalledWith('/user/content/recommendations', {
        params: { page: 1, page_size: 5 }
      })
    })

    it('默认分页', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userContentApi.listRecommendations()
      expect(request.get).toHaveBeenCalledWith('/user/content/recommendations', {
        params: { page: 1, page_size: 10 }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userContentApi.listRecommendations()).rejects.toThrow('500')
    })
  })

  describe('listRecentViews', () => {
    it('调用 GET /user/content/recent-views', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userContentApi.listRecentViews({ page: 2, page_size: 8 })
      expect(request.get).toHaveBeenCalledWith('/user/content/recent-views', {
        params: { page: 2, page_size: 8 }
      })
    })

    it('默认分页', async () => {
      (requestPageData as any).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 })
      await userContentApi.listRecentViews()
      expect(request.get).toHaveBeenCalledWith('/user/content/recent-views', {
        params: { page: 1, page_size: 10 }
      })
    })

    it('错误透传', async () => {
      (requestPageData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userContentApi.listRecentViews()).rejects.toThrow('500')
    })
  })

  describe('logMeditation', () => {
    it('通过 POST /user/content/meditation/log 记录冥想完成', async () => {
      (requestData as any).mockResolvedValueOnce({ log_id: 99 })
      const res = await userContentApi.logMeditation(12, true)
      expect(request.post).toHaveBeenCalledWith('/user/content/meditation/log', {
        content_id: 12,
        completed: true
      })
      expect(res).toEqual({ log_id: 99 })
    })

    it('completed=false 表示未完成', async () => {
      (requestData as any).mockResolvedValueOnce({ log_id: 1 })
      await userContentApi.logMeditation(0, false)
      expect(request.post).toHaveBeenCalledWith('/user/content/meditation/log', {
        content_id: 0,
        completed: false
      })
    })

    it('错误透传', async () => {
      (requestData as any).mockRejectedValueOnce(new Error('500'))
      await expect(userContentApi.logMeditation(1, true)).rejects.toThrow('500')
    })
  })
})

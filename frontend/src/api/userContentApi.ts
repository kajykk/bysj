import request, { requestData, requestPageData } from './request'
import { buildPageParams } from './business.shared'
import type { PageQuery } from '@/types/api'
import type { ContentDetail, ContentItem } from './userTypes'

export const userContentApi = {
  listContents: (query?: PageQuery & { category?: string; content_type?: string; keyword?: string }) =>
    requestPageData<ContentItem>(request.get('/user/content/', { params: { ...buildPageParams(query), category: query?.category, content_type: query?.content_type, keyword: query?.keyword } })),
  getContentDetail: (contentId: number) => requestData<ContentDetail>(request.get(`/user/content/${contentId}`)),
  toggleFavorite: (contentId: number) => requestData<{ message: string }>(request.post(`/user/content/${contentId}/favorite`)),
  listFavorites: (query?: PageQuery) => requestPageData<ContentItem>(request.get('/user/content/favorites/list', { params: buildPageParams(query) })),
  listRecommendations: (query?: PageQuery) => requestPageData<ContentItem>(request.get('/user/content/recommendations', { params: buildPageParams(query) })),
  listRecentViews: (query?: PageQuery) => requestPageData<ContentItem>(request.get('/user/content/recent-views', { params: buildPageParams(query) })),
  logMeditation: (contentId: number, completed: boolean) => requestData<{ log_id: number }>(request.post('/user/content/meditation/log', { content_id: contentId, completed })),
}

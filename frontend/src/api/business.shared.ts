import type { PageQuery } from '@/types/api'

export const buildPageParams = (query?: PageQuery) => ({
  page: Math.max(1, query?.page || 1),
  page_size: Math.min(100, Math.max(1, query?.page_size || 10))
})

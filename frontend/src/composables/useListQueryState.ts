import { computed } from 'vue'
import { useRoute, useRouter, type LocationQueryRaw, type LocationQueryValueRaw } from 'vue-router'

export function useListQueryState(prefix: string) {
  const route = useRoute()
  const router = useRouter()

  const key = (name: string) => `${prefix}_${name}`

  const getNumber = (name: string, fallback: number) => {
    const value = Number(route.query[key(name)])
    return Number.isFinite(value) && value > 0 ? value : fallback
  }

  const getString = (name: string, fallback = '') => {
    const value = route.query[key(name)]
    return typeof value === 'string' ? value : fallback
  }

  const setQuery = async (patch: Record<string, string | number | undefined>) => {
    const nextQuery: LocationQueryRaw = { ...route.query }
    Object.entries(patch).forEach(([k, v]) => {
      const full = key(k)
      if (v === undefined || v === '') {
        delete nextQuery[full]
      } else {
        nextQuery[full] = String(v) as LocationQueryValueRaw
      }
    })
    await router.replace({ query: nextQuery })
  }

  return {
    page: computed(() => getNumber('page', 1)),
    pageSize: computed(() => getNumber('page_size', 10)),
    getString,
    setQuery
  }
}

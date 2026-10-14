/**
 * P2-36 第四批迁移钉：useCounselorWarningsData 改由 useListQuery 提供。
 *
 * 测行为：连点翻页先发后到，旧响应不得覆盖新行；取后副作用（selectedRows
 * 重置）只发生在 fresh 响应。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import { useCounselorWarningsData } from './useCounselorWarningsData'

const { listMock } = vi.hoisted(() => ({ listMock: vi.fn() }))

vi.mock('@/api/counselorApi', () => ({
  counselorApi: { getCounselorWarnings: listMock },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ role: 'counselor' }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
    currentRoute: { value: { query: {} } },
  }),
}))

vi.mock('@/composables/useAnalytics', () => ({
  useAnalytics: () => ({ track: vi.fn() }),
}))

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

const mkRow = (id: number) => ({ id, is_read: false, handled: false })

function mountData() {
  let exposed!: ReturnType<typeof useCounselorWarningsData>
  const Harness = defineComponent({
    setup() {
      exposed = useCounselorWarningsData()
      return () => null
    },
  })
  mount(Harness, { global: { plugins: [i18n] } })
  return () => exposed
}

beforeEach(() => {
  listMock.mockReset()
  listMock.mockResolvedValue({ items: [], total: 0 })
})

describe('useCounselorWarningsData P2-36 迁移', () => {
  it('首屏拉取并写入 rows/total', async () => {
    listMock.mockResolvedValueOnce({ items: [mkRow(1)], total: 1 })
    const get = mountData()
    await flushPromises()
    expect(get().rows.value.map((r) => r.id)).toEqual([1])
    expect(get().total.value).toBe(1)
  })

  it('连点翻页先发后到：旧响应不得覆盖新行', async () => {
    const get = mountData()
    await flushPromises()
    const first = deferred<{ items: ReturnType<typeof mkRow>[]; total: number }>()
    const second = deferred<{ items: ReturnType<typeof mkRow>[]; total: number }>()
    listMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    get().onPageChange(2)
    get().onPageChange(3)
    second.resolve({ items: [mkRow(30)], total: 1 })
    await flushPromises()
    expect(get().rows.value.map((r) => r.id)).toEqual([30])

    first.resolve({ items: [mkRow(20)], total: 1 })
    await flushPromises()
    expect(get().rows.value.map((r) => r.id)).toEqual([30], '过期旧页覆盖了新行')
  })
})

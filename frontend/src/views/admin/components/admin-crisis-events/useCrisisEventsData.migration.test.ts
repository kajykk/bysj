/**
 * P2-36 第三批迁移钉：useCrisisEventsData 改由 useListQuery 提供三态 + 竞态守卫。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import { useCrisisEventsData } from './useCrisisEventsData'

const { listMock } = vi.hoisted(() => ({ listMock: vi.fn() }))

vi.mock('@/api/adminApi', () => ({
  adminApi: { getCrisisEvents: listMock },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
    currentRoute: { value: { query: {} } },
  }),
}))

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

const mkRow = (id: number) => ({ id, level: 'high' })

function mountData() {
  let exposed!: ReturnType<typeof useCrisisEventsData>
  const Harness = defineComponent({
    setup() {
      exposed = useCrisisEventsData()
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

describe('useCrisisEventsData P2-36 迁移', () => {
  it('首屏经 onMounted 拉取', async () => {
    listMock.mockResolvedValueOnce({ items: [mkRow(1)], total: 1 })
    const get = mountData()
    await flushPromises()
    expect(get().rows.value.map((r: { id: number }) => r.id)).toEqual([1])
    expect(get().total.value).toBe(1)
  })

  it('连点翻页先发后到：旧页不得覆盖新页', async () => {
    const get = mountData()
    await flushPromises()
    const first = deferred<{ items: { id: number }[]; total: number }>()
    const second = deferred<{ items: { id: number }[]; total: number }>()
    listMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    get().onPageChange(2)
    get().onPageChange(3)
    second.resolve({ items: [mkRow(30)], total: 1 })
    await flushPromises()
    expect(get().rows.value.map((r: { id: number }) => r.id)).toEqual([30])

    first.resolve({ items: [mkRow(20)], total: 1 })
    await flushPromises()
    expect(get().rows.value.map((r: { id: number }) => r.id)).toEqual([30], '过期旧页覆盖了新页')
  })

  it('失败写入 pageError', async () => {
    listMock.mockRejectedValueOnce(new Error('boom'))
    const get = mountData()
    await flushPromises()
    // 首屏失败
    expect(get().pageError.value).not.toBe('')
  })
})

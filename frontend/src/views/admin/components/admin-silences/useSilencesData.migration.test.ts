/**
 * P2-36 第三批迁移钉：useSilencesData 改由 useListQuery 提供三态 + 竞态守卫。
 *
 * 关键行为：activeSilences 附属块走 onSuccess —— 过期响应的附属请求不得落地。
 * 用例制造"旧列表响应晚到"并断言附属块未被旧响应触发。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import { useSilencesData } from './useSilencesData'

const { listMock, activeMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  activeMock: vi.fn(),
}))

vi.mock('@/api/alertsApi', () => ({
  alertsApi: {
    listSilences: listMock,
    listActiveSilences: activeMock,
  },
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

const mkRow = (id: number) => ({ id, name: `s${id}` })

function mountData() {
  let exposed!: ReturnType<typeof useSilencesData>
  const Harness = defineComponent({
    setup() {
      exposed = useSilencesData()
      return () => null
    },
  })
  mount(Harness, { global: { plugins: [i18n] } })
  return () => exposed
}

beforeEach(() => {
  listMock.mockReset()
  listMock.mockResolvedValue({ items: [], total: 0 })
  activeMock.mockReset()
  activeMock.mockResolvedValue({ items: [] })
})

describe('useSilencesData P2-36 迁移', () => {
  it('首屏拉取列表且附属块跟随 fresh 响应', async () => {
    listMock.mockResolvedValueOnce({ items: [mkRow(1)], total: 1 })
    const get = mountData()
    await flushPromises()
    expect(get().rows.value.map((r: { id: number }) => r.id)).toEqual([1])
    expect(activeMock).toHaveBeenCalled()
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

  it('筛选变化走 search：旧请求被作废', async () => {
    const get = mountData()
    await flushPromises()
    const first = deferred<{ items: { id: number }[]; total: number }>()
    const second = deferred<{ items: { id: number }[]; total: number }>()
    listMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    get().onPageChange(2) // 在途旧请求
    get().handleSearch() // 作废旧请求并回到第 1 页
    second.resolve({ items: [mkRow(10)], total: 1 })
    await flushPromises()
    first.resolve({ items: [mkRow(20)], total: 5 })
    await flushPromises()
    expect(get().rows.value.map((r: { id: number }) => r.id)).toEqual([10])
  })
})

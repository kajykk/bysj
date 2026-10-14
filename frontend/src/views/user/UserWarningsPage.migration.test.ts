/**
 * P2-36 第四批迁移钉：UserWarningsPage 改由 useListQuery 提供。
 *
 * 页面逻辑内联在 SFC 内，通过真实挂载 + 分页器 DOM 交互驱动：
 * 连点翻页制造先发后到，旧响应不得覆盖新行。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import UserWarningsPage from './UserWarningsPage.vue'

const { listMock } = vi.hoisted(() => ({ listMock: vi.fn() }))

vi.mock('@/api/userApi', () => ({
  userApi: { getUserWarnings: listMock },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ role: 'user' }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
    currentRoute: { value: { query: {} } },
  }),
}))

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub)

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

const mkRow = (id: number) => ({ id, is_read: false })

beforeEach(() => {
  listMock.mockReset()
  listMock.mockResolvedValue({ items: [], total: 0 })
})

describe('UserWarningsPage P2-36 迁移', () => {
  it('首屏渲染行数据', async () => {
    listMock.mockResolvedValueOnce({ items: [mkRow(1), mkRow(2)], total: 2 })
    const wrapper = mount(UserWarningsPage, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(listMock).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('连点翻页先发后到：旧响应不得覆盖新行', async () => {
    listMock.mockResolvedValueOnce({ items: [mkRow(1)], total: 1 })
    const wrapper = mount(UserWarningsPage, { global: { plugins: [i18n] } })
    await flushPromises()

    const first = deferred<{ items: ReturnType<typeof mkRow>[]; total: number }>()
    const second = deferred<{ items: ReturnType<typeof mkRow>[]; total: number }>()
    listMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const table = wrapper.findComponent({ name: 'PageTable' })
    expect(table.exists()).toBe(true)
    table.vm.$emit('update:page', 2)
    table.vm.$emit('update:page', 3)
    await flushPromises()

    second.resolve({ items: [mkRow(30)], total: 1 })
    await flushPromises()
    first.resolve({ items: [mkRow(20)], total: 1 })
    await flushPromises()

    expect(wrapper.text()).toContain('30')
    expect(wrapper.text()).not.toContain('20')
    wrapper.unmount()
  })
})

/**
 * P2-36 第六批迁移钉：AdminAlertsPage 改由 useListQuery 提供。
 *
 * 页面逻辑内联在 SFC 内，通过真实挂载 + 分页器 DOM 交互驱动：
 * 连点翻页制造先发后到，旧响应不得覆盖新行；切 tab 后数据源要同步切换
 * （history / archive 是两个不同端点，参数也不完全相同）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import AdminAlertsPage from './AdminAlertsPage.vue'

const { historyMock, archiveMock, statsMock } = vi.hoisted(() => ({
  historyMock: vi.fn(),
  archiveMock: vi.fn(),
  statsMock: vi.fn(),
}))

vi.mock('@/api/alertsApi', () => ({
  alertsApi: {
    listAlertHistory: historyMock,
    listAlertArchive: archiveMock,
    getAlertHistoryStats: statsMock,
    ackAlert: vi.fn(),
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

const mkRow = (id: number) => ({
  id,
  rule: `rule-${id}`,
  severity: 'P0',
  status: 'firing',
  message: `msg-${id}`,
  fingerprint: null,
  created_at: '2026-10-01T00:00:00',
})

const EMPTY_STATS = { total: 0, p0: 0, p1: 0, p2: 0, firing: 0, resolved: 0 }

beforeEach(() => {
  historyMock.mockReset()
  archiveMock.mockReset()
  statsMock.mockReset()
  historyMock.mockResolvedValue({ items: [], total: 0 })
  archiveMock.mockResolvedValue({ items: [], total: 0 })
  statsMock.mockResolvedValue(EMPTY_STATS)
})

describe('AdminAlertsPage P2-36 迁移', () => {
  it('首屏默认走 history 数据源', async () => {
    historyMock.mockResolvedValueOnce({ items: [mkRow(1), mkRow(2)], total: 2 })
    const wrapper = mount(AdminAlertsPage, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(historyMock).toHaveBeenCalledTimes(1)
    expect(archiveMock).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('连点翻页先发后到：旧响应不得覆盖新行', async () => {
    historyMock.mockResolvedValueOnce({ items: [mkRow(1)], total: 1 })
    const wrapper = mount(AdminAlertsPage, { global: { plugins: [i18n] } })
    await flushPromises()

    const first = deferred<{ items: ReturnType<typeof mkRow>[]; total: number }>()
    const second = deferred<{ items: ReturnType<typeof mkRow>[]; total: number }>()
    historyMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const table = wrapper.findComponent({ name: 'PageTable' })
    expect(table.exists()).toBe(true)
    table.vm.$emit('update:page', 2)
    table.vm.$emit('update:page', 3)
    await flushPromises()

    // 后发的第 3 页先回来（id 用 300/200，避免与日期串 "2026-..." 撞子串）
    second.resolve({ items: [mkRow(300)], total: 1 })
    await flushPromises()
    // 先发的第 2 页后回来，必须被竞态守卫丢弃
    first.resolve({ items: [mkRow(200)], total: 1 })
    await flushPromises()

    expect(wrapper.text()).toContain('300')
    expect(wrapper.text()).not.toContain('200')
    wrapper.unmount()
  })

  it('切到 archive 后改走归档数据源', async () => {
    historyMock.mockResolvedValueOnce({ items: [mkRow(1)], total: 1 })
    const wrapper = mount(AdminAlertsPage, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(archiveMock).not.toHaveBeenCalled()

    const radioGroup = wrapper.findComponent({ name: 'ElRadioGroup' })
    expect(radioGroup.exists()).toBe(true)
    await radioGroup.vm.$emit('change', 'archive')
    await flushPromises()

    expect(archiveMock).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})

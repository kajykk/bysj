/**
 * P2-36 第六批迁移钉：UserAssessmentsPage 改由 useListQuery 提供。
 *
 * 本页有两个「响应附属块」——表格行由 `toAssessmentHistoryRows` 映射，
 * 但详情页要用的**原始项** `rawItems` 与 sessionStorage 快照必须同步更新。
 * 迁移前它们写在 try 块里，过期响应晚到会把旧页的原始项留下来（详情页
 * 打开的就是别的记录）；迁移后由 `onSuccess` 只在确认 fresh 时写入。
 *
 * 因此本钉除了连点翻页竞态，还额外锁「附属块只由最新响应写入」。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import UserAssessmentsPage from './UserAssessmentsPage.vue'
import { CACHE_KEY, readCachedAssessmentItem } from './utils/assessmentDetailCache'

const { listMock } = vi.hoisted(() => ({ listMock: vi.fn() }))

vi.mock('@/api/userApi', () => ({
  userApi: { getUserAssessmentHistory: listMock },
}))

// withMockFallback 短路：本钉只关心列表时序，不引入 mock 数据源的分支
vi.mock('@/utils/mockFallback', () => ({
  withMockFallback: (fn: () => Promise<unknown>) => fn(),
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

const mkItem = (id: number) => ({
  id,
  type: 'structured',
  created_at: '2026-10-01T00:00:00',
  data: { score: 50, severity: 'high', assessment_type: 'PHQ-9' },
})

type PageResult = { items: ReturnType<typeof mkItem>[]; total: number }

beforeEach(() => {
  listMock.mockReset()
  listMock.mockResolvedValue({ items: [], total: 0 })
  sessionStorage.clear()
})

describe('UserAssessmentsPage P2-36 迁移', () => {
  it('首屏渲染行数据', async () => {
    listMock.mockResolvedValueOnce({ items: [mkItem(1), mkItem(2)], total: 2 })
    const wrapper = mount(UserAssessmentsPage, {
      global: { plugins: [i18n], stubs: { AssessmentsStatsCard: true } },
    })
    await flushPromises()
    expect(listMock).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('连点翻页先发后到：旧响应不得覆盖新行', async () => {
    listMock.mockResolvedValueOnce({ items: [mkItem(1)], total: 1 })
    const wrapper = mount(UserAssessmentsPage, {
      global: { plugins: [i18n], stubs: { AssessmentsStatsCard: true } },
    })
    await flushPromises()

    const first = deferred<PageResult>()
    const second = deferred<PageResult>()
    listMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const table = wrapper.findComponent({ name: 'PageTable' })
    expect(table.exists()).toBe(true)
    table.vm.$emit('update:page', 2)
    table.vm.$emit('update:page', 3)
    await flushPromises()

    // 后发的第 3 页先回来（id 用 300/200，避免与日期串 "2026-..." 撞子串）
    second.resolve({ items: [mkItem(300)], total: 1 })
    await flushPromises()
    // 先发的第 2 页后回来，必须被竞态守卫丢弃
    first.resolve({ items: [mkItem(200)], total: 1 })
    await flushPromises()

    expect(wrapper.text()).toContain('300')
    expect(wrapper.text()).not.toContain('200')
    wrapper.unmount()
  })

  it('过期响应不得写详情页快照（附属块只由最新响应写入）', async () => {
    listMock.mockResolvedValueOnce({ items: [mkItem(1)], total: 1 })
    const wrapper = mount(UserAssessmentsPage, {
      global: { plugins: [i18n], stubs: { AssessmentsStatsCard: true } },
    })
    await flushPromises()

    const first = deferred<PageResult>()
    const second = deferred<PageResult>()
    listMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const table = wrapper.findComponent({ name: 'PageTable' })
    table.vm.$emit('update:page', 2)
    table.vm.$emit('update:page', 3)
    await flushPromises()

    second.resolve({ items: [mkItem(300)], total: 1 })
    await flushPromises()
    first.resolve({ items: [mkItem(200)], total: 1 })
    await flushPromises()

    expect(readCachedAssessmentItem(CACHE_KEY, 300)).not.toBeNull()
    expect(readCachedAssessmentItem(CACHE_KEY, 200)).toBeNull()
    wrapper.unmount()
  })
})

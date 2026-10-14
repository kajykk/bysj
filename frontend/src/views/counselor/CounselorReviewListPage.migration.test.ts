/**
 * P2-36 第六批迁移钉：CounselorReviewListPage 改由 useListQuery 提供。
 *
 * 本页的三个特殊之处，正是钉子要锁的：
 * 1. 不写 URL query，page / pageSize 是本地 ref —— `setPage` 只改本地状态，
 *    「重置筛选回到第 1 页」必须真的回到第 1 页（原实现靠手抄 `page.value = 1`）；
 * 2. 列表失败走 ElMessage 而非页面错误槽，迁移后不能丢；
 * 3. 列表之外还有独立的统计卡与两个分配对话框，迁移不能波及它们的取数。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import CounselorReviewListPage from './CounselorReviewListPage.vue'

const { listMock, statsMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  statsMock: vi.fn(),
}))

vi.mock('@/api/counselorApi', () => ({
  counselorApi: {
    getReviews: listMock,
    getReviewStats: statsMock,
    assignReview: vi.fn(),
    getAssignableCounselors: vi.fn(),
  },
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
  user_id: 7,
  risk_level: 3,
  priority: 'high_risk_review',
  status: 'pending',
  crisis_override: false,
  review_triggers: ['manual'],
  created_at: '2026-10-01T00:00:00',
})

type PageResult = { items: ReturnType<typeof mkRow>[]; total: number }

const EMPTY_STATS = {
  total: 0,
  pending: 0,
  in_review: 0,
  resolved: 0,
  escalated: 0,
  crisis_count: 0,
  high_risk_count: 0,
}

function lastQuery() {
  const calls = listMock.mock.calls
  return calls[calls.length - 1][0] as { page: number; page_size: number }
}

beforeEach(() => {
  listMock.mockReset()
  statsMock.mockReset()
  // total 保持 100（5 页）：el-pagination 会在 total 变小把 currentPage 拉回 1，
  // 那样就翻不到第 3 页，竞态场景构造不出来。
  listMock.mockResolvedValue({ items: [], total: 100 })
  statsMock.mockResolvedValue(EMPTY_STATS)
})

describe('CounselorReviewListPage P2-36 迁移', () => {
  it('首屏渲染行数据', async () => {
    listMock.mockResolvedValueOnce({ items: [mkRow(1), mkRow(2)], total: 2 })
    const wrapper = mount(CounselorReviewListPage, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(listMock).toHaveBeenCalledTimes(1)
    expect(statsMock).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('连点翻页先发后到：旧响应不得覆盖新行', async () => {
    listMock.mockResolvedValueOnce({ items: [mkRow(1)], total: 100 })
    const wrapper = mount(CounselorReviewListPage, { global: { plugins: [i18n] } })
    await flushPromises()

    const first = deferred<PageResult>()
    const second = deferred<PageResult>()
    listMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const pagination = wrapper.findComponent({ name: 'ElPagination' })
    expect(pagination.exists()).toBe(true)
    // 真实点击「下一页」两下：el-pagination 内部更新 currentPage 并触发 @change
    await pagination.find('.btn-next').trigger('click')
    await flushPromises()
    await pagination.find('.btn-next').trigger('click')
    await flushPromises()

    // 后发的第 3 页先回来（id 用 300/200，避免与日期串 "2026-..." 撞子串）
    second.resolve({ items: [mkRow(300)], total: 100 })
    await flushPromises()
    // 先发的第 2 页后回来，必须被竞态守卫丢弃
    first.resolve({ items: [mkRow(200)], total: 100 })
    await flushPromises()

    expect(wrapper.text()).toContain('300')
    expect(wrapper.text()).not.toContain('200')
    wrapper.unmount()
  })

  it('重置筛选回到第 1 页（setPage 接线）', async () => {
    listMock.mockResolvedValueOnce({ items: [mkRow(1)], total: 100 })
    const wrapper = mount(CounselorReviewListPage, { global: { plugins: [i18n] } })
    await flushPromises()

    const pagination = wrapper.findComponent({ name: 'ElPagination' })
    await pagination.find('.btn-next').trigger('click')
    await flushPromises()
    await pagination.find('.btn-next').trigger('click')
    await flushPromises()
    expect(lastQuery().page).toBe(3)

    const resetButton = wrapper
      .findAllComponents({ name: 'ElButton' })
      .find((btn) => btn.text().includes('重置'))
    expect(resetButton).toBeTruthy()
    await resetButton!.trigger('click')
    await flushPromises()

    expect(lastQuery().page).toBe(1)
    wrapper.unmount()
  })
})

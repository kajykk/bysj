/**
 * P2-36 第二批迁移钉：useInterventionData 的 history 块改由 useListQuery 提供。
 *
 * 保持 lazy 语义（只在首次激活 history tab 时拉取）；测行为：
 * - tab 激活 + 翻页的交错响应里，旧响应不得覆盖新数据；
 * - 对外契约名不变（historyRows/historyError/loadHistory/handleTabChange/onPageChange）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import { useInterventionData } from './useInterventionData'

const { historyMock, activeMock } = vi.hoisted(() => ({
  historyMock: vi.fn(),
  activeMock: vi.fn(),
}))

vi.mock('@/api/userApi', () => ({
  userApi: {
    getInterventionHistory: historyMock,
    getActiveIntervention: activeMock,
  },
}))

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

const mkItem = (planId: number) => ({
  plan_id: planId,
  plan_name: `p${planId}`,
  status: 'active',
  start_date: null,
  end_date: null,
  completion_rate: 0,
  risk_change: 0,
  dominant_modality: null,
})

function mountData() {
  let exposed!: ReturnType<typeof useInterventionData>
  const Harness = defineComponent({
    setup() {
      exposed = useInterventionData()
      return () => null
    },
  })
  mount(Harness, { global: { plugins: [i18n] } })
  return () => exposed
}

beforeEach(() => {
  historyMock.mockReset()
  historyMock.mockResolvedValue({ items: [], total: 0 })
  activeMock.mockReset()
  activeMock.mockResolvedValue({
    plan: { id: 1, plan_name: 'p', risk_level: 1, start_date: null, progress: 0 },
    tasks: [],
  })
})

describe('useInterventionData history P2-36 迁移', () => {
  it('挂载时不拉 history（lazy），首次激活 tab 才拉', async () => {
    const get = mountData()
    await flushPromises()
    expect(historyMock).not.toHaveBeenCalled()
    get().handleTabChange('history')
    await flushPromises()
    expect(historyMock).toHaveBeenCalledTimes(1)
  })

  it('激活后翻页交错：旧响应不得覆盖新数据', async () => {
    const get = mountData()
    await flushPromises()
    get().handleTabChange('history')
    await flushPromises()
    expect(get().historyRows.value).toEqual([])

    const first = deferred<{ items: ReturnType<typeof mkItem>[]; total: number }>()
    const second = deferred<{ items: ReturnType<typeof mkItem>[]; total: number }>()
    historyMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    get().onPageChange(2)
    get().onPageChange(3)
    second.resolve({ items: [mkItem(30)], total: 1 })
    await flushPromises()
    expect(get().historyRows.value.map((r) => r.plan_id)).toEqual([30])

    first.resolve({ items: [mkItem(20)], total: 1 })
    await flushPromises()
    expect(get().historyRows.value.map((r) => r.plan_id)).toEqual([30], '过期旧页覆盖了新页')
  })
})

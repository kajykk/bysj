/**
 * P2-36 第二批迁移钉：useTemplatesData 改由 useListQuery 提供三态 + 竞态守卫。
 *
 * 不测"调没调 useListQuery"（形式断言），测行为：
 * - 连点翻页制造先发后到，旧页响应不得覆盖新页 rows（迁移存在的唯一理由）；
 * - 失败走 pageError 对外契约（页面 StatefulContainer 绑的是这个名）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'
import { useTemplatesData } from './useTemplatesData'

const { listMock } = vi.hoisted(() => ({ listMock: vi.fn() }))

vi.mock('@/api/adminApi', () => ({
  adminApi: { listAdminTemplates: listMock },
}))

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const mkRow = (id: number) => ({
  id,
  template_name: `t${id}`,
  applicable_levels: [],
  task_list: [],
  estimated_weeks: 1,
  status: 'active',
})

function mountData() {
  let exposed!: ReturnType<typeof useTemplatesData>
  const Harness = defineComponent({
    setup() {
      exposed = useTemplatesData()
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

describe('useTemplatesData P2-36 迁移', () => {
  it('首屏经 onMounted 拉取并写入 rows/total', async () => {
    listMock.mockResolvedValueOnce({ items: [mkRow(1)], total: 1 })
    const get = mountData()
    await flushPromises()
    expect(get().rows.value.map((r) => r.id)).toEqual([1])
    expect(get().total.value).toBe(1)
    expect(get().loading.value).toBe(false)
  })

  it('连点翻页先发后到：旧页响应不得覆盖新页', async () => {
    const get = mountData()
    await flushPromises() // 首屏那次先落定
    const first = deferred<{ items: ReturnType<typeof mkRow>[]; total: number }>()
    const second = deferred<{ items: ReturnType<typeof mkRow>[]; total: number }>()
    listMock.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    get().handlePageChange(2)
    get().handlePageChange(3)
    second.resolve({ items: [mkRow(30)], total: 1 })
    await flushPromises()
    expect(get().rows.value.map((r) => r.id)).toEqual([30])

    first.resolve({ items: [mkRow(20)], total: 1 })
    await flushPromises()
    expect(get().rows.value.map((r) => r.id)).toEqual([30], '过期旧页覆盖了新页')
  })

  it('失败写入 pageError（页面错误槽契约不变）', async () => {
    listMock.mockRejectedValueOnce(new Error('boom'))
    const get = mountData()
    await flushPromises()
    expect(get().pageError.value).not.toBe('')
    expect(get().rows.value).toEqual([])
  })
})

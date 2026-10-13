/**
 * P2-36: useListQuery 闸门。
 *
 * 反假闸门设计（沿用项目纪律）：
 * - **竞态守卫不测"函数存在"，测"过期响应确实没落地"** —— 先发后到的旧响应
 *   若被写入 rows，断言必须红（这是本 composable 存在的唯一理由）。
 * - 三态各自独立断言：loading / error / empty 不能互相冒充。
 * - 每个用例都驱动真实时序（可控 deferred promise），不做形式化快照。
 */
import { describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import { useListQuery } from '@/composables/useListQuery'

/** 构造一个可手动控制的请求，用于制造"先发后到"的竞态。 */
function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const mkList = (n: number, prefix = 'r') => ({
  items: Array.from({ length: n }, (_, i) => ({ id: `${prefix}${i}` })),
  total: n,
})

describe('useListQuery 竞态守卫', () => {
  it('过期响应不得覆盖新响应（先发后到）', async () => {
    const first = deferred<{ items: { id: string }[]; total: number }>()
    const second = deferred<{ items: { id: string }[]; total: number }>()
    const fetcher = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    const q = useListQuery<{ id: string }>({ fetcher, immediate: false })

    const p1 = q.run()
    const p2 = q.run()
    expect(fetcher).toHaveBeenCalledTimes(2)

    // 后到的反而先返回
    second.resolve(mkList(2, 'new'))
    await p2
    expect(q.rows.value.map((r) => r.id)).toEqual(['new0', 'new1'])

    // 先发的现在才返回 —— 必须被丢弃
    first.resolve(mkList(5, 'old'))
    await p1
    await nextTick()
    expect(q.rows.value.map((r) => r.id)).toEqual(['new0', 'new1']), '过期响应覆盖了新数据'
    expect(q.total.value).toBe(2)
  })

  it('过期响应不得提前关掉 loading', async () => {
    const first = deferred<{ items: { id: string }[]; total: number }>()
    const second = deferred<{ items: { id: string }[]; total: number }>()
    const fetcher = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const q = useListQuery<{ id: string }>({ fetcher, immediate: false })

    const p1 = q.run()
    const p2 = q.run()
    first.resolve(mkList(1, 'old'))
    await p1
    expect(q.loading.value).toBe(true), '旧请求返回就把 loading 关掉了（会闪一下空态）'
    second.resolve(mkList(1, 'new'))
    await p2
    expect(q.loading.value).toBe(false)
  })
})

describe('useListQuery 三态', () => {
  it('加载中 loading=true，成功后为 false 且 empty 正确', async () => {
    const d = deferred<{ items: { id: string }[]; total: number }>()
    const q = useListQuery<{ id: string }>({ fetcher: () => d.promise, immediate: false })
    expect(q.loaded.value).toBe(false)
    expect(q.empty.value).toBe(false), '从未加载过不应算 empty'

    const p = q.run()
    expect(q.loading.value).toBe(true)
    d.resolve({ items: [], total: 0 })
    await p
    expect(q.loading.value).toBe(false)
    expect(q.loaded.value).toBe(true)
    expect(q.empty.value).toBe(true), '加载过且 0 条才算 empty'
  })

  it('失败写入 error 文案，且不把 empty 当失败', async () => {
    const q = useListQuery<{ id: string }>({
      fetcher: () => Promise.reject(new Error('boom')),
      onError: () => '加载失败(测试)',
      immediate: false,
    })
    await q.run()
    expect(q.error.value).toBe('加载失败(测试)')
    expect(q.empty.value).toBe(false), '失败态不能被误判成空态'
    expect(q.loading.value).toBe(false)
  })
})

describe('useListQuery 页码重置', () => {
  it('search() 先重置到第 1 页再拉取', async () => {
    const setPage = vi.fn()
    const fetcher = vi.fn().mockResolvedValue(mkList(1))
    const q = useListQuery<{ id: string }>({ fetcher, setPage, immediate: false })
    await q.search()
    expect(setPage).toHaveBeenCalledWith(1)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('search() 会作废在途请求，旧页响应不得落地', async () => {
    const first = deferred<{ items: { id: string }[]; total: number }>()
    const pages: number[] = []
    const page = ref(1)
    const fetcher = vi
      .fn()
      .mockImplementationOnce(() => {
        pages.push(page.value)
        return first.promise
      })
      .mockImplementationOnce(() => {
        pages.push(page.value)
        return Promise.resolve(mkList(1, 'p1'))
      })
    const q = useListQuery<{ id: string }>({
      fetcher,
      setPage: (p) => {
        page.value = p
      },
      immediate: false,
    })
    const p1 = q.run()
    await q.search()
    expect(page.value).toBe(1)
    // 让旧的（page=5 场景）响应返回
    first.resolve(mkList(3, 'stale'))
    await p1
    await nextTick()
    expect(q.rows.value.map((r) => r.id)).toEqual(['p10'])
  })

  it('search() 的作废窗口：第二次请求失败时，在途旧响应不得留在表里', async () => {
    // 这条用例专门盯住 search() 里那句 `seq += 1`。
    // 没有它：旧响应会在 `await setPage` 的窗口里落地；若紧接着的第二次请求又失败，
    // 用户会看到「上一次的旧数据 + 失败提示」，且该旧数据来自已被作废的查询条件。
    const first = deferred<{ items: { id: string }[]; total: number }>()
    let calls = 0
    const q = useListQuery<{ id: string }>({
      fetcher: () => (calls++ === 0 ? first.promise : Promise.reject(new Error('search failed'))),
      setPage: async () => {
        first.resolve(mkList(3, 'stale')) // 旧响应正好在 setPage 的 await 窗口内返回
        await new Promise((r) => setTimeout(r, 0))
      },
      onError: () => 'E',
      immediate: false,
    })
    const p1 = q.run()
    await q.search()
    await p1
    await nextTick()
    expect(q.error.value).toBe('E')
    expect(q.rows.value).toEqual([]), '在途旧响应留下了（search 的作废窗口失效）'
  })

  it('reset() 清空结果并作废在途请求', async () => {
    const d = deferred<{ items: { id: string }[]; total: number }>()
    const q = useListQuery<{ id: string }>({ fetcher: () => d.promise, immediate: false })
    const p = q.run()
    q.reset()
    d.resolve(mkList(2))
    await p
    await nextTick()
    expect(q.rows.value).toEqual([])
    expect(q.loaded.value).toBe(false)
  })
})

describe('useListQuery 其它约定', () => {
  it('immediate 默认挂载即拉一次', async () => {
    const fetcher = vi.fn().mockResolvedValue(mkList(1))
    useListQuery<{ id: string }>({ fetcher })
    await nextTick()
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('onSuccess 只在响应未过期时调用', async () => {
    const first = deferred<{ items: { id: string }[]; total: number }>()
    const second = deferred<{ items: { id: string }[]; total: number }>()
    const onSuccess = vi.fn()
    const q = useListQuery<{ id: string }>({
      fetcher: () => (fetcherCalls++ === 0 ? first.promise : second.promise),
      onSuccess,
      immediate: false,
    })
    let fetcherCalls = 0
    const p1 = q.run()
    const p2 = q.run()
    second.resolve(mkList(1))
    await p2
    expect(onSuccess).toHaveBeenCalledTimes(1)
    first.resolve(mkList(1))
    await p1
    await nextTick()
    expect(onSuccess).toHaveBeenCalledTimes(1), '过期响应不应触发 onSuccess'
  })
})

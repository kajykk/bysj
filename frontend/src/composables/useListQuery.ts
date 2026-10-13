/**
 * P2-36: 列表页统一查询 composable —— 内置竞态守卫 + 页码重置 + 三态。
 *
 * 背景（审查报告 P2-36）：12 个列表页各自复制了一份「loading ref + try/catch/finally
 * + rows/total 赋值」，约 700 行重复，且**三处共性缺陷每份都各自漂移**：
 *
 *   1. **无竞态守卫**：`onPageChange` / `handleSearch` 直接调 `fetchData()`，
 *      快速连点翻页时多个响应交错返回，先发后到的旧响应会覆盖新页数据；
 *   2. **页码重置靠手抄**：筛选条件变化后是否 `page=1` 全凭作者记得与否，
 *      实测 12 页里只有少数几页写对；
 *   3. **三态不完整**：多数页面只有 `loading`，没有独立的 `error` / `empty` 态，
 *      失败与「真的 0 条」在 UI 上无法区分（与 P1-15 空 catch 吞错同型）。
 *
 * 设计约定：
 * - **不接管参数组装**：各页筛选形态差异极大（reactive 对象 / URL query / 枚举），
 *   由调用方在 `fetcher` 闭包里组装，composable 只管时序与状态；
 * - **竞态守卫用单调序号**：每次 run 取一个 token，响应回来时 token 过期即丢弃
 *   （不写 rows / 不改 loading），天然覆盖「连点翻页」「筛选后旧请求晚到」两类；
 * - **错误文案由调用方提供** `onError`（返回要展示的文案），保证 i18n 留在页面里；
 * - 本 composable 与既有的 `useListQueryState`（URL query 持久化）**分工不同**：
 *   那个管"筛选条件存哪儿"，这个管"请求怎么发、状态怎么表达"，可叠加使用。
 */
import { computed, ref, type Ref } from 'vue'

export interface ListResult<T> {
  items: T[]
  total: number
}

export interface UseListQueryOptions<T, R extends ListResult<T>> {
  /** 真正发请求的函数（由调用方闭包组装参数） */
  fetcher: () => Promise<R>
  /**
   * 仅在「响应未被竞态作废」时调用。
   * 用于写入响应里的附属块（如统计卡 compliance）—— 直接写在 fetcher 里会
   * 被过期响应污染，故必须由 composable 在确认 fresh 之后回调。
   */
  onSuccess?: (res: R) => void
  /** 筛选条件变化后的页码重置回调（通常写入 URL query state） */
  setPage?: (page: number) => Promise<void> | void
  /** 挂载即拉一次，默认 true */
  immediate?: boolean
  /** 把异常转成展示文案；不提供则 error 为空串（页面自行提示） */
  onError?: (error: unknown) => string
}

export interface UseListQueryReturn<T> {
  rows: Ref<T[]>
  total: Ref<number>
  /** 三态之一：正在加载 */
  loading: Ref<boolean>
  /** 三态之一：失败文案（空串 = 无错误） */
  error: Ref<string>
  /** 三态之一：已成功加载过且当前无数据（与「从未加载」区分开） */
  empty: Ref<boolean>
  /** 是否至少成功加载过一次 */
  loaded: Ref<boolean>
  run: () => Promise<void>
  /** 筛选条件变化后调用：先重置到第 1 页再拉取 */
  search: () => Promise<void>
  /** 清空结果（用于筛选全清 / 切换上下文） */
  reset: () => void
}

export function useListQuery<T, R extends ListResult<T> = ListResult<T>>(
  options: UseListQueryOptions<T, R>
): UseListQueryReturn<T> {
  const rows = ref<T[]>([]) as Ref<T[]>
  const total = ref(0)
  const loading = ref(false)
  const error = ref('')
  const loaded = ref(false)

  // 竞态守卫：单调递增的请求序号。过期响应一律丢弃。
  let seq = 0

  const empty = computed(
    () => loaded.value && !loading.value && !error.value && rows.value.length === 0
  )

  const run = async (): Promise<void> => {
    const token = ++seq
    loading.value = true
    error.value = ''
    try {
      const res = await options.fetcher()
      if (token !== seq) return // 已有更新的请求发出，丢弃本次响应
      rows.value = res.items ?? []
      total.value = res.total ?? 0
      loaded.value = true
      options.onSuccess?.(res)
    } catch (err) {
      if (token !== seq) return
      error.value = options.onError?.(err) ?? ''
      loaded.value = true
    } finally {
      // 只有"自己是最新请求"才收尾，否则会把新请求的 loading 提前关掉
      if (token === seq) {
        loading.value = false
      }
    }
  }

  const search = async (): Promise<void> => {
    // 竞态守卫的另一半：先作废在途请求，避免旧页响应晚到覆盖第 1 页
    seq += 1
    await options.setPage?.(1)
    await run()
  }

  const reset = (): void => {
    seq += 1
    rows.value = []
    total.value = 0
    loaded.value = false
    error.value = ''
    loading.value = false
  }

  if (options.immediate !== false) {
    void run()
  }

  return { rows, total, loading, error, empty, loaded, run, search, reset }
}

/**
 * R-E3: ECharts 生命周期 composable.
 *
 * 封装 initChartWhenReady 重试链 + subscribeResize 共享监听 + 卸载 dispose，
 * 渲染通过 optionBuilder 回调惰性构建（避免组件内联超长 option）。
 */

import { nextTick, onUnmounted, ref, watch, type Ref } from 'vue'
import type { ECharts } from '@/utils/echarts'
import { subscribeResize } from '@/utils/sharedResize'
import { initChartWhenReady, type ChartInitHandle } from '@/utils/chartInit'

interface UseChartOptions {
  getOption: () => Record<string, unknown>
  /** 触发重渲染的响应式依赖 */
  deps: Array<Ref<unknown> | (() => unknown)>
  retries?: number
  intervalMs?: number
}

export function useTrendChart(opts: UseChartOptions) {
  const containerRef = ref<HTMLElement>()
  let chart: ECharts | null = null
  let renderSeq = 0
  let initHandle: ChartInitHandle | null = null
  let unsubscribeResize: (() => void) | null = null
  let isUnmounted = false

  const dispose = () => {
    initHandle?.cancel()
    initHandle = null
    unsubscribeResize?.()
    unsubscribeResize = null
    chart?.dispose()
    chart = null
  }

  const render = async () => {
    await nextTick()
    const el = containerRef.value
    if (!el || isUnmounted) return

    if (chart) {
      dispose()
    } else {
      // 无实例但可能存在未完成的重试链，取消后重建
      initHandle?.cancel()
      initHandle = null
    }
    // 容器尺寸就绪后才 init（避免 0 尺寸初始化警告）；
    // seq 防止 dispose 后过期的延迟 init 回调覆盖新实例
    const seq = ++renderSeq
    initHandle = initChartWhenReady(
      el,
      { retries: opts.retries ?? 5, intervalMs: opts.intervalMs ?? 100 },
      (instance) => {
        // 回调到达时组件已卸载/已过期 → 立即释放实例
        if (isUnmounted || seq !== renderSeq) {
          instance.dispose()
          return
        }
        chart = instance
        unsubscribeResize = subscribeResize(() => chart?.resize())
        instance.setOption(opts.getOption())
      },
    )
  }

  watch(opts.deps, () => {
    render()
  })

  onUnmounted(() => {
    isUnmounted = true
    dispose()
  })

  return { containerRef, render, dispose }
}

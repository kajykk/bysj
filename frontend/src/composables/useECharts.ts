import { onBeforeUnmount, onMounted } from 'vue'
import { echarts, type ECharts, type EChartsCoreOption } from '@/utils/echarts'
import { subscribeResize } from '@/utils/sharedResize'

/**
 * ECharts composable.
 *
 * P1-D-9 修复：chartInstances 从模块级单例改为函数内部作用域，
 * 使每个调用 useECharts() 的组件实例拥有独立的 Map，
 * 避免任一组件卸载时意外销毁其他组件的图表实例。
 */
export function useECharts() {
  const chartInstances = new Map<string, ECharts>()

  const registerChart = (key: string, dom: HTMLElement | null, option?: EChartsCoreOption): ECharts | null => {
    if (!dom) return null

    disposeChart(key)

    const instance = echarts.init(dom)
    if (option) {
      instance.setOption(option)
    }

    chartInstances.set(key, instance)
    return instance
  }

  const updateChart = (key: string, option: EChartsCoreOption): void => {
    const instance = chartInstances.get(key)
    if (instance) {
      instance.setOption(option, true)
    }
  }

  const disposeChart = (key: string): void => {
    const instance = chartInstances.get(key)
    if (instance) {
      instance.dispose()
      chartInstances.delete(key)
    }
  }

  const disposeAllCharts = (): void => {
    chartInstances.forEach((instance) => {
      instance.dispose()
    })
    chartInstances.clear()
  }

  const resizeChart = (key: string): void => {
    const instance = chartInstances.get(key)
    if (instance) {
      instance.resize()
    }
  }

  const resizeAllCharts = (): void => {
    chartInstances.forEach((instance) => {
      instance.resize()
    })
  }

  onBeforeUnmount(() => {
    disposeAllCharts()
  })

  return {
    registerChart,
    updateChart,
    disposeChart,
    disposeAllCharts,
    resizeChart,
    resizeAllCharts,
  }
}

/**
 * 图表 resize 监听 composable.
 *
 * P1-D-9 修复：接收 resizeAll 回调而非引用模块级 Map，
 * 与 useECharts 实例级 Map 设计保持一致。
 *
 * @param resizeAll - 触发所有图表 resize 的回调函数
 */
// L-FE-15 修复：resizeAll 标注为必填，空函数默认值无实际意义且会掩盖调用遗漏
export function useChartResize(resizeAll: () => void) {
  // L-FE-2 修复：使用共享 resize 监听，避免每个图表组件实例独立注册
  let unsubscribe: (() => void) | null = null

  onMounted(() => {
    unsubscribe = subscribeResize(resizeAll)
  })

  onBeforeUnmount(() => {
    unsubscribe?.()
  })
}

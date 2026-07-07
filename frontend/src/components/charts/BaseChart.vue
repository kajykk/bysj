<template>
  <div
    ref="chartRef"
    class="base-chart"
    :style="chartStyle"
    role="img"
    :aria-label="effectiveAriaLabel"
    tabindex="0"
    @keydown.enter="handleEnter"
    @keydown.space="handleSpace"
  />
</template>

<script setup lang="ts">
import { computed, ref, shallowRef, onMounted, onUnmounted, onActivated, onDeactivated, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
// H-12 修复：改用 @/utils/echarts 统一入口，避免重复注册组件，
// 同时获得 HeatmapChart/VisualMapComponent 等图表支持（R-007 移除未使用的 RadarChart）。
// ISS-086 TODO：图表高度目前依赖父组件传入固定像素值，移动端可考虑根据视口高度自适应（如 min(40vh, 300px)）
// ISS-097 已修复：图表容器已具备 role="img" 与 aria-label（默认值取自 i18n charts.baseAriaLabel）
// ISS-098 TODO：复杂多系列图表可补充 aria-describedby 关联数据摘要文本，提升屏幕阅读器信息完整性
// ISS-100 已修复：图表容器已具备 role="img" 与 aria-label，并支持键盘 Enter/Space 触发 highlight
import { echarts, type ECharts, type EChartsCoreOption } from '@/utils/echarts'

const { t } = useI18n()

interface Props {
  option: EChartsCoreOption
  width?: string
  height?: string
  theme?: string
  autoResize?: boolean
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  width: '100%',
  height: '300px',
  theme: undefined,
  autoResize: true,
  ariaLabel: undefined,
})

const emit = defineEmits<{
  chartReady: [chart: ECharts]
}>()

const chartRef = ref<HTMLDivElement>()
// FM-02 修复：使用 shallowRef 持有 ECharts 实例和 ResizeObserver。
// shallowRef 避免 Vue 对大型第三方对象进行深度响应式代理（性能开销且可能触发 ECharts 内部警告），
// 同时保持 per-instance 作用域语义（<script setup> 中每个实例独立）。
const chartInstance = shallowRef<ECharts | null>(null)
const resizeObserver = shallowRef<ResizeObserver | null>(null)
// R-009 修复：使用 rAF 合并同一帧内的多次 ResizeObserver 回调，
// 避免 ECharts resize 的同步布局计算阻塞主线程（尤其多图表页面）。
let resizeRafId: number | null = null

const chartStyle = computed(() => ({
  width: props.width,
  height: props.height,
}))

const effectiveAriaLabel = computed(() => props.ariaLabel ?? t('charts.baseAriaLabel'))

const validExportTypes = ['png', 'svg', 'jpeg'] as const

const initChart = () => {
  if (!chartRef.value) return

  chartInstance.value = echarts.init(chartRef.value, props.theme)
  // L-07 修复：处理空 option，避免渲染空白图表
  if (props.option && Object.keys(props.option).length > 0) {
    chartInstance.value.setOption(props.option, true)
  }
  emit('chartReady', chartInstance.value)

  // 响应式调整
  if (props.autoResize) {
    resizeObserver.value = new ResizeObserver(() => {
      // R-009 修复：ResizeObserver 在布局变化时高频回调（含 sidebar 折叠、flex 变化等），
      // 直接调用 chart.resize() 会同步触发 ECharts 布局重计算。
      // 使用 requestAnimationFrame 将 resize 合并到下一帧，同一帧内多次回调只执行一次。
      if (resizeRafId !== null) return
      resizeRafId = requestAnimationFrame(() => {
        resizeRafId = null
        chartInstance.value?.resize()
      })
    })
    resizeObserver.value.observe(chartRef.value)
  }
}

const disposeChart = () => {
  if (resizeRafId !== null) {
    cancelAnimationFrame(resizeRafId)
    resizeRafId = null
  }
  if (resizeObserver.value && chartRef.value) {
    resizeObserver.value.unobserve(chartRef.value)
    resizeObserver.value.disconnect()
  }
  chartInstance.value?.dispose()
  chartInstance.value = null
}

// H-16 修复：原仅监听引用变化，但部分父组件直接修改 option 内部字段不会触发更新。
// M-FE-6 修复：添加 { deep: true } 以捕获 option 内部字段变更，确保图表同步刷新。
watch(
  () => props.option,
  (newOption) => {
    if (chartInstance.value && newOption && Object.keys(newOption).length > 0) {
      chartInstance.value.setOption(newOption, true)
    }
  },
  { deep: true }
)

// L-FE-16 修复：onMounted 已在 DOM 挂载后执行，无需再套 nextTick
onMounted(() => {
  initChart()
})

// C-FE-4 修复：keep-alive 组件需要处理 onActivated/onDeactivated。
// 否则 deactivate 时实例与 ResizeObserver 不会被清理（内存泄漏），
// reactivate 时也不会重新初始化（图表空白）。
onActivated(() => {
  // 仅在实例已被清理时重新初始化（keep-alive 缓存但未卸载时 chartInstance 仍存在）
  if (!chartInstance.value && chartRef.value) {
    nextTick(() => initChart())
  }
})

onDeactivated(() => {
  disposeChart()
})

onUnmounted(() => {
  disposeChart()
})

// 键盘事件处理
const handleEnter = () => {
  chartInstance.value?.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: 0 })
}
const handleSpace = (event: KeyboardEvent) => {
  event.preventDefault()
  handleEnter()
}

// 暴露方法
defineExpose({
  getInstance: () => chartInstance.value,
  resize: () => chartInstance.value?.resize(),
  setOption: (option: EChartsCoreOption) => chartInstance.value?.setOption(option, true),
  exportImage: (type: (typeof validExportTypes)[number] = 'png', pixelRatio = 2) => {
    return chartInstance.value?.getDataURL({ type, pixelRatio })
  },
})
</script>

<style scoped>
.base-chart {
  width: 100%;
}
</style>

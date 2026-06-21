<template>
  <div
    ref="chartRef"
    class="base-chart"
    :style="chartStyle"
    role="img"
    :aria-label="ariaLabel"
    tabindex="0"
    @keydown.enter="handleEnter"
    @keydown.space="handleSpace"
  />
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  ToolboxComponent,
  DataZoomComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ECharts, EChartsCoreOption } from 'echarts/core'

// 注册必要的组件
echarts.use([
  LineChart,
  BarChart,
  PieChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  ToolboxComponent,
  DataZoomComponent,
  CanvasRenderer,
])

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
  ariaLabel: '数据图表',
})

const emit = defineEmits<{
  chartReady: [chart: ECharts]
}>()

const chartRef = ref<HTMLDivElement>()
let chartInstance: ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const chartStyle = computed(() => ({
  width: props.width,
  height: props.height,
}))

const validExportTypes = ['png', 'svg', 'jpeg'] as const

const initChart = () => {
  if (!chartRef.value) return

  chartInstance = echarts.init(chartRef.value, props.theme)
  chartInstance.setOption(props.option, true)
  emit('chartReady', chartInstance)

  // 响应式调整
  if (props.autoResize) {
    resizeObserver = new ResizeObserver(() => {
      chartInstance?.resize()
    })
    resizeObserver.observe(chartRef.value)
  }
}

const disposeChart = () => {
  if (resizeObserver && chartRef.value) {
    resizeObserver.unobserve(chartRef.value)
    resizeObserver.disconnect()
  }
  chartInstance?.dispose()
  chartInstance = null
}

// 监听配置变化
watch(
  () => props.option,
  (newOption) => {
    if (chartInstance) {
      chartInstance.setOption(newOption, true)
    }
  },
  { deep: true }
)

onMounted(() => {
  nextTick(() => initChart())
})

onUnmounted(() => {
  disposeChart()
})

// 键盘事件处理
const handleEnter = () => {
  chartInstance?.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: 0 })
}

const handleSpace = (event: KeyboardEvent) => {
  event.preventDefault()
  handleEnter()
}

// 暴露方法
defineExpose({
  getInstance: () => chartInstance,
  resize: () => chartInstance?.resize(),
  setOption: (option: EChartsCoreOption) => chartInstance?.setOption(option, true),
  exportImage: (type: (typeof validExportTypes)[number] = 'png', pixelRatio = 2) => {
    return chartInstance?.getDataURL({ type, pixelRatio })
  },
})
</script>

<style scoped>
.base-chart {
  width: 100%;
}
</style>

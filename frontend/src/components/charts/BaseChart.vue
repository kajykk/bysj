<template>
  <div
    ref="hostRef"
    class="base-chart"
    :style="chartStyle"
    role="img"
    :aria-label="effectiveAriaLabel"
    :aria-describedby="hasDescription ? describedById : undefined"
    tabindex="0"
    @keydown.enter="handleEnter"
    @keydown.space="handleSpace"
  >
    <span
      v-if="hasDescription"
      :id="describedById"
      class="sr-only"
    >{{ description }}</span>
    <VChart
      v-if="active && hostReady"
      ref="chartRef"
      class="base-chart__canvas"
      :option="chartOption"
      :theme="effectiveTheme"
      :autoresize="props.autoResize"
      :update-options="updateOptions"
      @finished="handleFinished"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, ref, useId, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'
import VChart from 'vue-echarts'
import 'vue-echarts/style.css'
import type { EChartsOption } from 'echarts'
// 运行时副作用：注册按需图表与 CanvasRenderer，VChart 与业务共用同一份 echarts/core 单例
import '@/utils/echarts'
// H-12 修复：改用 @/utils/echarts 统一入口，避免重复注册组件。
// ISS-086 TODO：图表高度目前依赖父组件传入固定像素值，移动端可考虑根据视口高度自适应。
// ISS-097/ISS-100 已修复：容器具备 role="img"、aria-label 与键盘 Enter/Space 高亮。
// ISS-098 TODO：复杂多系列图表可补充 aria-describedby 关联数据摘要文本。
import { type ECharts, type EChartsCoreOption } from '@/utils/echarts'
import { chartEchartsTheme, chartThemeVersion } from '@/utils/chartTheme'

const { t } = useI18n()

interface Props {
  option: EChartsCoreOption
  width?: string
  height?: string
  theme?: string | Record<string, unknown>
  autoResize?: boolean
  ariaLabel?: string
  chartId?: string
  description?: string
}

const props = withDefaults(defineProps<Props>(), {
  width: '100%',
  height: '300px',
  theme: undefined,
  autoResize: true,
  ariaLabel: undefined,
  chartId: undefined,
  description: undefined,
})

const emit = defineEmits<{
  chartReady: [chart: ECharts]
}>()

interface VChartExposed {
  readonly chart?: ECharts
  resize: () => void
  dispatchAction: (payload: unknown) => void
  getDataURL: (opts: { type: string; pixelRatio: number }) => string
}

const hostRef = useTemplateRef<HTMLDivElement>('hostRef')
const chartRef = useTemplateRef<VChartExposed>('chartRef')

const chartStyle = computed(() => ({
  width: props.width,
  height: props.height,
}))

const effectiveAriaLabel = computed(() => props.ariaLabel ?? t('charts.baseAriaLabel'))

// A11Y-P2-08 修复：role="img" 关联 aria-describedby，提供图表数据摘要描述
const generatedChartId = useId()
const effectiveChartId = computed(() => props.chartId || `chart-${generatedChartId}`)
const describedById = computed(() => `${effectiveChartId.value}-desc`)
const hasDescription = computed(() => Boolean(props.description))

const chartOption = computed(() => (props.option ?? {}) as unknown as EChartsOption)
const updateOptions = { notMerge: true }

const effectiveTheme = computed(() => {
  // 主题切换计数是依赖项：html.dark 变化时换新主题对象，触发 VChart 重新初始化
  void chartThemeVersion.value
  return props.theme ?? chartEchartsTheme()
})

// SEC-FIX (P1-6)：容器尺寸就绪后才挂载 VChart，避免 0 尺寸初始化警告与空白 canvas。
// 测试环境 jsdom 无布局引擎，保持同步挂载以维持既有断言。
const hostReady = ref(import.meta.env.MODE === 'test')
const active = ref(true)
let hostObserver: ResizeObserver | null = null

const measureHost = () => {
  const el = hostRef.value
  if (!el) return
  if (el.clientWidth > 0 && el.clientHeight > 0) {
    hostReady.value = true
    hostObserver?.disconnect()
    hostObserver = null
  }
}

onMounted(() => {
  measureHost()
  if (hostReady.value || !hostRef.value || typeof ResizeObserver === 'undefined') return
  hostObserver = new ResizeObserver(measureHost)
  hostObserver.observe(hostRef.value)
})

// C-FE-4 修复：keep-alive 停用时卸载 VChart（随组件销毁实例与 ResizeObserver），
// 激活后重新挂载，避免隐藏页持有 canvas 与监听器。
onActivated(() => {
  active.value = true
  nextTick(measureHost)
})

onDeactivated(() => {
  active.value = false
})

onUnmounted(() => {
  hostObserver?.disconnect()
  hostObserver = null
})

let readyChart: ECharts | null = null

const handleFinished = () => {
  const chart = chartRef.value?.chart
  if (!chart || chart === readyChart) return
  readyChart = chart
  emit('chartReady', chart)
}

const handleEnter = () => {
  chartRef.value?.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: 0 })
}

const handleSpace = (event: KeyboardEvent) => {
  event.preventDefault()
  handleEnter()
}

const validExportTypes = ['png', 'svg', 'jpeg'] as const

defineExpose({
  getInstance: () => chartRef.value?.chart ?? null,
  resize: () => chartRef.value?.resize(),
  setOption: (option: EChartsCoreOption) => chartRef.value?.chart?.setOption(option, true),
  exportImage: (type: (typeof validExportTypes)[number] = 'png', pixelRatio = 2) => {
    return chartRef.value?.chart?.getDataURL({ type, pixelRatio })
  },
})
</script>

<style scoped>
.base-chart {
  width: 100%;
}

.base-chart__canvas {
  width: 100%;
  height: 100%;
}

/* A11Y-P2-08：图表数据摘要描述，仅供屏幕阅读器读取，视觉隐藏 */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>

<template>
  <el-card v-if="data.length || loading">
    <template #header>
      <span class="card-title">{{ t('experimentAssess.accuracyChartTitle') }}</span>
    </template>
    <div
      v-if="loading"
      class="chart-skeleton"
    >
      <el-skeleton
        :rows="5"
        animated
      />
    </div>
    <div
      v-else
      ref="chartRef"
      class="chart-box"
    />
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { echarts, type ECharts } from '@/utils/echarts'
import { subscribeResize } from '@/utils/sharedResize'
import { CHART_COLORS } from './sharedChartUtils'

const props = defineProps<{
  data: number[]
  loading: boolean
}>()

const { t } = useI18n()

const chartRef = ref<HTMLElement>()
let chart: ECharts | null = null

const buildOption = (data: number[]) => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: data.map((_, i) => `E${i + 1}`) },
  yAxis: { type: 'value', min: 0, max: 1 },
  series: [{
    type: 'line',
    smooth: true,
    data,
    lineStyle: { width: 2, color: CHART_COLORS.accuracy },
    areaStyle: { opacity: 0.15 },
  }],
})

const render = () => {
  if (chartRef.value && props.data.length) {
    chart ??= echarts.init(chartRef.value)
    chart.setOption(buildOption(props.data))
  }
}

// R-009 修复：使用 subscribeResize 共享全局节流 resize 监听，避免每个图表组件独立注册
let unsubscribeResize: (() => void) | null = null

watch([() => props.data, () => props.loading], () => {
  render()
}, { flush: 'post' })

onMounted(() => {
  unsubscribeResize = subscribeResize(() => chart?.resize())
  render()
})

onUnmounted(() => {
  unsubscribeResize?.()
  unsubscribeResize = null
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.chart-box {
  width: 100%;
  height: 280px;
}

.chart-skeleton {
  padding: 20px;
}

.card-title {
  font-weight: 600;
}
</style>

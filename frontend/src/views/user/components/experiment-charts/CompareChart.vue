<template>
  <el-card v-if="data.length || loading">
    <template #header>
      <span class="card-title">{{ t('experimentAssess.compareChartTitle') }}</span>
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
      class="chart-box chart-box-lg"
    />
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { echarts, type ECharts } from '@/utils/echarts'
import { subscribeResize } from '@/utils/sharedResize'
import { CHART_COLORS, COMPARE_METRICS, type CompareItem } from './sharedChartUtils'

const props = defineProps<{
  data: CompareItem[]
  loading: boolean
}>()

const { t } = useI18n()

const chartRef = ref<HTMLElement>()
let chart: ECharts | null = null

const buildOption = (data: CompareItem[]) => ({
  tooltip: { trigger: 'axis' },
  legend: { data: [...COMPARE_METRICS] },
  grid: { left: 50, right: 20, top: 30, bottom: 60 },
  xAxis: { type: 'category', data: data.map(i => i.model_name) },
  yAxis: { type: 'value', min: 0, max: 1 },
  series: COMPARE_METRICS.map((key, idx) => ({
    name: key,
    type: 'bar',
    data: data.map(item => item[key]),
    itemStyle: { color: CHART_COLORS.compareSeries[idx] },
  })),
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

.chart-box-lg {
  height: 340px;
}

.chart-skeleton {
  padding: 20px;
}

.card-title {
  font-weight: 600;
}
</style>

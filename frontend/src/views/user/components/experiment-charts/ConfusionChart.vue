<template>
  <el-card v-if="data.length || loading">
    <template #header>
      <span class="card-title">{{ t('experimentAssess.confusionChartTitle') }}</span>
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

const props = defineProps<{
  data: number[][]
  loading: boolean
}>()

const { t } = useI18n()

const chartRef = ref<HTMLElement>()
let chart: ECharts | null = null

const buildOption = (data: number[][]) => ({
  tooltip: {},
  xAxis: { type: 'category', data: ['Pred 0', 'Pred 1'] },
  yAxis: { type: 'category', data: ['True 0', 'True 1'] },
  visualMap: {
    min: 0,
    max: Math.max(...data.flat(), 1),
    calculable: true,
    orient: 'horizontal',
    left: 'center',
    bottom: 0,
  },
  series: [{
    type: 'heatmap',
    data: [
      [0, 0, data[0][0]],
      [1, 0, data[0][1]],
      [0, 1, data[1][0]],
      [1, 1, data[1][1]],
    ],
    label: { show: true },
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

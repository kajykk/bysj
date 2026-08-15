<template>
  <el-card v-if="data.length || loading">
    <template #header>
      <span class="card-title">{{ t('experimentAssess.compareChartTitle') }}</span>
    </template>
    <div
      v-if="loading"
      class="chart-skeleton"
    >
      <SkeletonScreen
        :rows="5"
        variant="text"
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
import SkeletonScreen from '@/components/common/SkeletonScreen.vue'
import { type ECharts } from '@/utils/echarts'
import { initChartWhenReady, type ChartInitHandle } from '@/utils/chartInit'
import { subscribeResize } from '@/utils/sharedResize'
import { CHART_COLORS, COMPARE_METRICS, type CompareItem } from './sharedChartUtils'

const props = defineProps<{
  data: CompareItem[]
  loading: boolean
}>()

const { t } = useI18n()

const chartRef = ref<HTMLElement>()
let chart: ECharts | null = null
// SEC-FIX (P1-6): 记录 init 句柄, 卸载时取消未完成的重试链
let initHandle: ChartInitHandle | null = null

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
  const target = chartRef.value
  if (!target || !props.data.length) return
  if (!chart) {
    // 容器尺寸就绪后才 init（避免 0 尺寸初始化警告）；就绪后回调内渲染
    initHandle = initChartWhenReady(target, {}, (instance) => {
      // SEC-FIX (P1-6): 已存在实例 (重复 init 竞态) → 释放新实例
      if (chart) {
        instance.dispose()
        return
      }
      chart = instance
      chart.setOption(buildOption(props.data))
    })
    return
  }
  chart.setOption(buildOption(props.data))
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
  // SEC-FIX (P1-6): 取消未完成的重试链, 防止对已卸载 DOM 创建僵尸实例
  initHandle?.cancel()
  initHandle = null
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

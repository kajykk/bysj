<template>
  <el-card v-if="data.length || loading">
    <template #header>
      <span class="card-title">{{ t('experimentAssess.accuracyChartTitle') }}</span>
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
      class="chart-box"
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
import { CHART_COLORS } from './sharedChartUtils'

const props = defineProps<{
  data: number[]
  loading: boolean
}>()

const { t } = useI18n()

const chartRef = ref<HTMLElement>()
let chart: ECharts | null = null
// SEC-FIX (P1-6): 记录 init 句柄, 卸载时取消未完成的重试链
let initHandle: ChartInitHandle | null = null

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

.chart-skeleton {
  padding: 20px;
}

.card-title {
  font-weight: 600;
}
</style>

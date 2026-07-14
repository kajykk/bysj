<template>
  <BaseChart
    :option="chartOption"
    :height="height"
    :auto-resize="autoResize"
    @chart-ready="handleChartReady"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseChart from './BaseChart.vue'
import { chartColors } from '@/utils/chartTheme'
import type { EChartsCoreOption } from 'echarts/core'

const { t } = useI18n()

interface HealthDataPoint {
  time: string
  successRate: number
  fallbackRate: number
  latency: number
}

interface Props {
  data: HealthDataPoint[]
  height?: string
  title?: string
  autoResize?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  height: '300px',
  title: undefined,
  autoResize: true,
})

const effectiveTitle = computed(() => props.title ?? t('charts.systemHealthTitle'))

const emit = defineEmits<{
  chartReady: [instance: unknown]
}>()

const handleChartReady = (instance: unknown) => {
  emit('chartReady', instance)
}

const chartOption = computed<EChartsCoreOption>(() => {
  const times = props.data.map((d) => d.time)
  // 统一读取设计令牌，避免硬编码旧主色 #3b82c4 与全局主色不一致
  const c = chartColors()

  return {
    title: {
      text: effectiveTitle.value,
      left: 'center',
      textStyle: {
        fontSize: 16,
        fontWeight: 'normal',
      },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
      },
    },
    legend: {
      bottom: 0,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      top: '15%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: times,
      boundaryGap: false,
    },
    yAxis: [
      {
        type: 'value',
        name: t('charts.yAxisRatio'),
        min: 0,
        max: 100,
        position: 'left',
        axisLabel: {
          formatter: '{value}%',
        },
      },
      {
        type: 'value',
        name: t('charts.yAxisLatency'),
        min: 0,
        position: 'right',
        axisLabel: {
          formatter: '{value} ms',
        },
      },
    ],
    toolbox: {
      feature: {
        saveAsImage: {
          title: t('charts.saveImage'),
        },
        dataZoom: {
          title: {
            zoom: t('charts.zoomIn'),
            back: t('charts.zoomReset'),
          },
        },
      },
    },
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100,
      },
    ],
    series: [
      {
        name: t('charts.seriesSuccessRate'),
        type: 'line',
        data: props.data.map((d) => d.successRate),
        smooth: true,
        yAxisIndex: 0,
        lineStyle: { width: 2, color: c.success },
        itemStyle: { color: c.success },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: c.successAreaStart },
              { offset: 1, color: c.successAreaEnd },
            ],
          },
        },
      },
      {
        name: t('charts.seriesFallbackRate'),
        type: 'line',
        data: props.data.map((d) => d.fallbackRate),
        smooth: true,
        yAxisIndex: 0,
        lineStyle: { width: 2, color: c.danger },
        itemStyle: { color: c.danger },
      },
      {
        name: t('charts.seriesLatency'),
        type: 'line',
        data: props.data.map((d) => d.latency),
        smooth: true,
        yAxisIndex: 1,
        lineStyle: { width: 2, color: c.primary, type: 'dashed' },
        itemStyle: { color: c.primary },
      },
    ],
  }
})
</script>

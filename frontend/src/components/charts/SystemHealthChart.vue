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
import BaseChart from './BaseChart.vue'
import type { EChartsCoreOption } from 'echarts/core'

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
  title: '系统健康监控',
  autoResize: true,
})

const emit = defineEmits<{
  chartReady: [instance: unknown]
}>()

const handleChartReady = (instance: unknown) => {
  emit('chartReady', instance)
}

const chartOption = computed<EChartsCoreOption>(() => {
  const times = props.data.map((d) => d.time)

  return {
    title: {
      text: props.title,
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
        name: '比率',
        min: 0,
        max: 100,
        position: 'left',
        axisLabel: {
          formatter: '{value}%',
        },
      },
      {
        type: 'value',
        name: '延迟 (ms)',
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
          title: '保存图片',
        },
        dataZoom: {
          title: {
            zoom: '区域缩放',
            back: '缩放还原',
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
        name: '成功率',
        type: 'line',
        data: props.data.map((d) => d.successRate),
        smooth: true,
        yAxisIndex: 0,
        lineStyle: { width: 2, color: '#67c23a' },
        itemStyle: { color: '#67c23a' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(103, 194, 58, 0.3)' },
              { offset: 1, color: 'rgba(103, 194, 58, 0.05)' },
            ],
          },
        },
      },
      {
        name: '回退率',
        type: 'line',
        data: props.data.map((d) => d.fallbackRate),
        smooth: true,
        yAxisIndex: 0,
        lineStyle: { width: 2, color: '#f56c6c' },
        itemStyle: { color: '#f56c6c' },
      },
      {
        name: '延迟',
        type: 'line',
        data: props.data.map((d) => d.latency),
        smooth: true,
        yAxisIndex: 1,
        lineStyle: { width: 2, color: '#409eff', type: 'dashed' },
        itemStyle: { color: '#409eff' },
      },
    ],
  }
})
</script>

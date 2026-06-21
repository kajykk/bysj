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

interface DataPoint {
  date: string
  value: number
  upperBound?: number
  lowerBound?: number
}

interface Props {
  data: DataPoint[]
  height?: string
  title?: string
  showBounds?: boolean
  autoResize?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  height: '300px',
  title: '风险趋势',
  showBounds: true,
  autoResize: true,
})

const emit = defineEmits<{
  chartReady: [instance: unknown]
}>()

const handleChartReady = (instance: unknown) => {
  emit('chartReady', instance)
}

const chartOption = computed<EChartsCoreOption>(() => {
  const dates = props.data.map((d) => d.date)
  const values = props.data.map((d) => d.value)
  const upperBounds = props.data.map((d) => d.upperBound)
  const lowerBounds = props.data.map((d) => d.lowerBound)

  const series: unknown[] = [
    {
      name: '风险值',
      type: 'line',
      data: values,
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: {
        width: 3,
        color: '#409eff',
      },
      itemStyle: {
        color: '#409eff',
      },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(64, 158, 255, 0.3)' },
            { offset: 1, color: 'rgba(64, 158, 255, 0.05)' },
          ],
        },
      },
    },
  ]

  if (props.showBounds && upperBounds.some((v) => v !== undefined)) {
    series.push({
      name: '上限',
      type: 'line',
      data: upperBounds,
      smooth: true,
      lineStyle: {
        width: 2,
        type: 'dashed',
        color: '#f56c6c',
      },
      itemStyle: {
        color: '#f56c6c',
      },
      symbol: 'none',
    })

    series.push({
      name: '下限',
      type: 'line',
      data: lowerBounds,
      smooth: true,
      lineStyle: {
        width: 2,
        type: 'dashed',
        color: '#67c23a',
      },
      itemStyle: {
        color: '#67c23a',
      },
      symbol: 'none',
    })
  }

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
      data: dates,
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1,
    },
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
      {
        start: 0,
        end: 100,
      },
    ],
    series,
  }
})
</script>

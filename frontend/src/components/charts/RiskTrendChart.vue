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
import type { EChartsCoreOption } from 'echarts/core'

const { t } = useI18n()

// ISS-076 修复：从 CSS 变量读取图表色板，消除硬编码 hex，与 variables.scss 令牌统一
const readChartVar = (name: string, fallback: string): string => {
  if (typeof window === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

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
  title: undefined,
  showBounds: true,
  autoResize: true,
})

const effectiveTitle = computed(() => props.title ?? t('charts.riskTrendTitle'))

const emit = defineEmits<{
  chartReady: [instance: unknown]
}>()

const handleChartReady = (instance: unknown) => {
  emit('chartReady', instance)
}

const chartOption = computed<EChartsCoreOption>(() => {
  // ISS-076 修复：图表配色读取 CSS 变量令牌，与 variables.scss 统一
  const colorPrimary = readChartVar('--chart-color-primary', '#3b82c4')
  const colorDanger = readChartVar('--chart-color-danger', '#d65a5a')
  const colorSuccess = readChartVar('--chart-color-success', '#5a9e3a')
  const areaStart = readChartVar('--chart-color-primary-area', 'rgba(59, 130, 196, 0.25)')
  const areaEnd = readChartVar('--chart-color-primary-area-end', 'rgba(59, 130, 196, 0.04)')

  const dates = props.data.map((d) => d.date)
  const values = props.data.map((d) => d.value)
  const upperBounds = props.data.map((d) => d.upperBound)
  const lowerBounds = props.data.map((d) => d.lowerBound)

  const series: unknown[] = [
    {
      name: t('charts.seriesRiskValue'),
      type: 'line',
      data: values,
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: {
        width: 3,
        color: colorPrimary,
      },
      itemStyle: {
        color: colorPrimary,
      },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: areaStart },
            { offset: 1, color: areaEnd },
          ],
        },
      },
    },
  ]

  if (props.showBounds && upperBounds.some((v) => v !== undefined)) {
    series.push({
      name: t('charts.seriesUpperBound'),
      type: 'line',
      data: upperBounds,
      smooth: true,
      lineStyle: {
        width: 2,
        type: 'dashed',
        color: colorDanger,
      },
      itemStyle: {
        color: colorDanger,
      },
      symbol: 'none',
    })

    series.push({
      name: t('charts.seriesLowerBound'),
      type: 'line',
      data: lowerBounds,
      smooth: true,
      lineStyle: {
        width: 2,
        type: 'dashed',
        color: colorSuccess,
      },
      itemStyle: {
        color: colorSuccess,
      },
      symbol: 'none',
    })
  }

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
      {
        start: 0,
        end: 100,
      },
    ],
    series,
  }
})
</script>

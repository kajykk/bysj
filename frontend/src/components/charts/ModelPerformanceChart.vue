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

interface ModelMetric {
  name: string
  accuracy: number
  precision: number
  recall: number
  f1: number
  auc: number
}

interface Props {
  data: ModelMetric[]
  height?: string
  title?: string
  autoResize?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  height: '300px',
  title: undefined,
  autoResize: true,
})

const effectiveTitle = computed(() => props.title ?? t('charts.modelPerformanceTitle'))

const emit = defineEmits<{
  chartReady: [instance: unknown]
}>()

const handleChartReady = (instance: unknown) => {
  emit('chartReady', instance)
}

const chartOption = computed<EChartsCoreOption>(() => {
  const models = props.data.map((d) => d.name)

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
        type: 'shadow',
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
      data: models,
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1,
      axisLabel: {
        formatter: '{value}',
      },
    },
    toolbox: {
      feature: {
        saveAsImage: {
          title: t('charts.saveImage'),
        },
      },
    },
    series: [
      {
        name: 'Accuracy',
        type: 'bar',
        data: props.data.map((d) => d.accuracy),
        itemStyle: { color: '#3b82c4' },
      },
      {
        name: 'Precision',
        type: 'bar',
        data: props.data.map((d) => d.precision),
        itemStyle: { color: '#5a9e3a' },
      },
      {
        name: 'Recall',
        type: 'bar',
        data: props.data.map((d) => d.recall),
        itemStyle: { color: '#d4923a' },
      },
      {
        name: 'F1',
        type: 'bar',
        data: props.data.map((d) => d.f1),
        itemStyle: { color: '#d65a5a' },
      },
      {
        name: 'AUC',
        type: 'bar',
        data: props.data.map((d) => d.auc),
        itemStyle: { color: '#7a8290' },
      },
    ],
  }
})
</script>

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
  title: '模型性能对比',
  autoResize: true,
})

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
          title: '保存图片',
        },
      },
    },
    series: [
      {
        name: 'Accuracy',
        type: 'bar',
        data: props.data.map((d) => d.accuracy),
        itemStyle: { color: '#409eff' },
      },
      {
        name: 'Precision',
        type: 'bar',
        data: props.data.map((d) => d.precision),
        itemStyle: { color: '#67c23a' },
      },
      {
        name: 'Recall',
        type: 'bar',
        data: props.data.map((d) => d.recall),
        itemStyle: { color: '#e6a23c' },
      },
      {
        name: 'F1',
        type: 'bar',
        data: props.data.map((d) => d.f1),
        itemStyle: { color: '#f56c6c' },
      },
      {
        name: 'AUC',
        type: 'bar',
        data: props.data.map((d) => d.auc),
        itemStyle: { color: '#909399' },
      },
    ],
  }
})
</script>

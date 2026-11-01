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
    <BaseChart
      v-else
      :option="chartOption"
      height="340px"
    />
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import SkeletonScreen from '@/components/common/SkeletonScreen.vue'
import BaseChart from '@/components/charts/BaseChart.vue'
import { useChartSeriesColors } from '@/utils/chartTheme'
import { COMPARE_METRICS, type CompareItem } from './sharedChartUtils'

const props = defineProps<{
  data: CompareItem[]
  loading: boolean
}>()

const { t } = useI18n()
const seriesColors = useChartSeriesColors()

const chartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: [...COMPARE_METRICS] },
  grid: { left: 50, right: 20, top: 30, bottom: 60 },
  xAxis: { type: 'category', data: props.data.map(i => i.model_name) },
  yAxis: { type: 'value', min: 0, max: 1 },
  series: COMPARE_METRICS.map((key, idx) => ({
    name: key,
    type: 'bar',
    data: props.data.map(item => item[key]),
    itemStyle: { color: seriesColors.value[idx % seriesColors.value.length] },
  })),
}))
</script>

<style scoped>
.chart-skeleton {
  padding: 20px;
}

.card-title {
  font-weight: 600;
}
</style>

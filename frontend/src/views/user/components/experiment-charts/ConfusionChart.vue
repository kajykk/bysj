<template>
  <el-card v-if="data.length || loading">
    <template #header>
      <span class="card-title">{{ t('experimentAssess.confusionChartTitle') }}</span>
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
import { useChartColors } from '@/utils/chartTheme'
import { withAlpha } from '@/utils/chartPalette'

const props = defineProps<{
  data: number[][]
  loading: boolean
}>()

const { t } = useI18n()
const colors = useChartColors()

const chartOption = computed(() => ({
  tooltip: {},
  xAxis: { type: 'category', data: ['Pred 0', 'Pred 1'] },
  yAxis: { type: 'category', data: ['True 0', 'True 1'] },
  visualMap: {
    min: 0,
    max: Math.max(...props.data.flat(), 1),
    calculable: true,
    orient: 'horizontal',
    left: 'center',
    bottom: 0,
    inRange: {
      color: [
        withAlpha(colors.value.primary, 0.06),
        colors.value.primary,
      ],
    },
  },
  series: [{
    type: 'heatmap',
    data: [
      [0, 0, props.data[0][0]],
      [1, 0, props.data[0][1]],
      [0, 1, props.data[1][0]],
      [1, 1, props.data[1][1]],
    ],
    label: { show: true },
  }],
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

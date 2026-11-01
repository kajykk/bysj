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
    <BaseChart
      v-else
      :option="chartOption"
      height="280px"
    />
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import SkeletonScreen from '@/components/common/SkeletonScreen.vue'
import BaseChart from '@/components/charts/BaseChart.vue'
import { useChartColors } from '@/utils/chartTheme'

const props = defineProps<{
  data: number[]
  loading: boolean
}>()

const { t } = useI18n()
const colors = useChartColors()

const chartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: props.data.map((_, i) => `E${i + 1}`) },
  yAxis: { type: 'value', min: 0, max: 1 },
  series: [{
    type: 'line',
    smooth: true,
    data: props.data,
    lineStyle: { width: 2, color: colors.value.success },
    areaStyle: { opacity: 0.15 },
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

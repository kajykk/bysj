<template>
  <section class="bento-cell bento-item">
    <header class="bento-cell__head bento-cell__head--split">
      <h3 class="bento-cell__title">
        {{ t('userDashboard.riskTrendTitle') }}
      </h3>
      <el-radio-group
        v-model="days"
        size="small"
        @change="emit('reload')"
      >
        <el-radio-button :value="7">
          {{ t('userDashboard.trendDays7') }}
        </el-radio-button>
        <el-radio-button :value="30">
          {{ t('userDashboard.trendDays30') }}
        </el-radio-button>
        <el-radio-button :value="90">
          {{ t('userDashboard.trendDays90') }}
        </el-radio-button>
      </el-radio-group>
    </header>
    <div
      v-if="loading"
      class="card-loading"
    >
      <el-skeleton
        :rows="4"
        animated
      />
    </div>
    <EmptyState
      v-else-if="error"
      :title="t('userDashboard.loadFailed')"
      :description="error"
      :image-size="60"
    >
      <template #action>
        <el-button
          type="primary"
          plain
          @click="emit('reload')"
        >
          {{ t('userDashboard.btnReload') }}
        </el-button>
      </template>
    </EmptyState>
    <EmptyState
      v-else-if="!riskTrend.points.length"
      :title="t('userDashboard.emptyNoTrend')"
      :description="t('userDashboard.emptyNoTrendDesc')"
      :image-size="60"
    />
    <div
      v-else
      ref="trendChartRef"
      class="trend-chart"
    />
  </section>
</template>

<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { echarts, type ECharts } from '@/utils/echarts'
import { subscribeResize } from '@/utils/sharedResize'
import { readChartVar } from '@/utils/chartTheme'
import EmptyState from '@/components/common/EmptyState.vue'
import type { RiskTrend } from '@/api/userRiskApi'
import {
  CHART_RISK_LEVEL_KEYS,
  CHART_TREND_KEYS,
  escapeHtml
} from './sharedDashboardUtils'

const props = defineProps<{
  riskTrend: RiskTrend
  loading: boolean
  error: string
}>()

const days = defineModel<number>('days', { default: 30 })
const emit = defineEmits<{ reload: [] }>()

const { t } = useI18n()

const trendChartRef = ref<HTMLElement>()
let trendChart: ECharts | null = null
// R-009 修复：使用 subscribeResize 共享全局节流 resize 监听，避免独立注册
let unsubscribeTrendResize: (() => void) | null = null

const disposeTrendChart = () => {
  unsubscribeTrendResize?.()
  unsubscribeTrendResize = null
  trendChart?.dispose()
  trendChart = null
}

const renderTrendChart = () => {
  if (!trendChartRef.value) return
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value)
    // R-009 修复：通过 subscribeResize 注册共享监听
    unsubscribeTrendResize = subscribeResize(() => trendChart?.resize())
  }
  const points = props.riskTrend.points

  // ISS-077 修复：图表配色读取 CSS 变量令牌，与 variables.scss 统一
  // VIS-P2-02 修复：tooltip 背景与边框改用主题令牌，深色模式下自动适配
  const chartDanger = readChartVar('--chart-color-danger', '#d65a5a')
  const chartTextPrimary = readChartVar('--text-primary', '#2c3340')
  const chartTextSecondary = readChartVar('--text-secondary', '#8a929e')
  const chartTooltipBg = readChartVar('--bg-primary', '#ffffff')
  const chartTooltipBorder = readChartVar('--border-color', '#dce1e7')

  trendChart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: chartTooltipBg,
      borderColor: chartTooltipBorder,
      borderWidth: 1,
      textStyle: { color: chartTextPrimary, fontSize: 13 },
      extraCssText: 'box-shadow: 0 4px 16px rgba(46, 111, 168, 0.08); border-radius: 8px;',
      formatter: (params: unknown) => {
        const p = (params as Array<{ dataIndex: number }>)[0]
        const point = points[p.dataIndex]
        if (!point) return ''
        const levelKey = CHART_RISK_LEVEL_KEYS[point.risk_level]
        const levelText = levelKey ? t(`userDashboard.${levelKey}`) : t('userDashboard.severityUnknown')
        const trendKey = CHART_TREND_KEYS[props.riskTrend.direction]
        const trendText = trendKey ? t(`userDashboard.${trendKey}`) : t('userDashboard.trendStable')
        const date = escapeHtml(point.date)
        const score = escapeHtml(point.risk_score)
        const level = escapeHtml(levelText)
        const trend = escapeHtml(trendText)
        const scoreLabel = t('userDashboard.chartRiskScoreLabel')
        const levelLabel = t('userDashboard.chartRiskLevelLabel')
        const trendLabel = t('userDashboard.chartOverallTrendLabel')
        const scoreUnit = t('userDashboard.scoreUnit')
        return `<div style="padding: 4px 2px;">
          <div style="font-weight:600;margin-bottom:6px;color:${chartTextPrimary};">${date}</div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${chartDanger};"></span>
            <span>${scoreLabel}<strong>${score}${scoreUnit}</strong></span>
          </div>
          <div style="margin-bottom:4px;padding-left:16px;">${levelLabel}<span style="color:${chartDanger};font-weight:500;">${level}</span></div>
          <div style="padding-left:16px;color:${chartTextSecondary};font-size:12px;">${trendLabel}${trend}</div>
        </div>`
      }
    },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: points.map((p) => p.date), axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { fontSize: 11 } },
    series: [{
      type: 'line',
      data: points.map((p) => p.risk_score),
      smooth: true,
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(214,90,90,0.25)' },
        { offset: 1, color: 'rgba(214,90,90,0.02)' }
      ]) },
      lineStyle: { color: chartDanger, width: 2 },
      itemStyle: { color: chartDanger },
      emphasis: {
        itemStyle: { borderWidth: 2, borderColor: '#fff', shadowBlur: 8, shadowColor: 'rgba(214,90,90,0.5)' },
        scale: 1.5
      }
    }]
  })
}

// 监听趋势数据变化，渲染或销毁图表（等价于原 loadRiskTrend finally 内的渲染分支）
watch(
  () => props.riskTrend,
  async () => {
    if (props.error || props.riskTrend.points.length === 0) {
      disposeTrendChart()
      return
    }
    await nextTick()
    renderTrendChart()
  }
)

onUnmounted(() => {
  disposeTrendChart()
})
</script>

<style scoped>
.bento-cell {
  background: var(--bg-primary);
  border: 1px solid var(--border-extra-light);
  border-radius: 1.25rem;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  box-shadow: 0 1px 2px rgba(15, 22, 32, 0.04);
  transition: box-shadow 0.3s var(--transition-ease-out),
    border-color 0.3s var(--transition-ease-out);
}

.bento-cell:hover {
  box-shadow: 0 12px 32px -12px rgba(46, 111, 168, 0.14);
  border-color: var(--border-light);
}

.bento-cell__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1.125rem;
}

.bento-cell__head--split {
  margin-bottom: 1rem;
}

.bento-cell__title {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: 0.9375rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.card-loading {
  padding: var(--spacing-lg) 0;
}

.trend-chart {
  height: 300px;
  width: 100%;
}
</style>

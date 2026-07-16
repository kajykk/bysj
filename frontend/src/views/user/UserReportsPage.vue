<!-- frontend/src/views/user/UserReportsPage.vue -->
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { userRiskApi } from '@/api/userRiskApi'
import { reportsApi } from '@/api/reportsApi'
import { showHttpFeedback } from '@/utils/httpFeedback'
import BaseChart from '@/components/charts/BaseChart.vue'
import type { EChartsCoreOption } from '@/utils/echarts'
import type { RiskReport, RiskTrend } from '@/api/userRiskApi'

const { t } = useI18n()
const report = ref<RiskReport | null>(null)
const trend = ref<RiskTrend | null>(null)
const days = ref(30)
const loading = ref(false)
const exporting = ref(false)

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const trendOption = computed<EChartsCoreOption>(() => {
  const points = trend.value?.points || []
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: points.map((p) => p.date) },
    yAxis: { type: 'value' },
    series: [{ name: t('user.riskScore'), type: 'line', data: points.map((p) => p.risk_score), smooth: true }],
  }
})

const FACTOR_COLORS = ['#2e6fa8', '#5a9e3a', '#d4923a', '#d65a5a', '#7a8290', '#82a9cb']
const factorOption = computed<EChartsCoreOption>(() => {
  const factors = (report.value?.main_factors || []).slice(0, 6)
  const data = factors.map((f) => ({ name: f.feature, value: Number(f.importance) || 0 }))
  if (!data.length) return {}
  return {
    tooltip: { trigger: 'item' },
    legend: { type: 'scroll', orient: 'vertical', right: 10, top: 'middle' },
    series: [{
      type: 'pie',
      radius: ['42%', '70%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      data: data.map((d, i) => ({ ...d, itemStyle: { color: FACTOR_COLORS[i % FACTOR_COLORS.length] } }))
    }]
  }
})

async function loadData() {
  loading.value = true
  try {
    const [r, tr] = await Promise.all([
      userRiskApi.getRiskReport(),
      userRiskApi.getRiskTrend(days.value),
    ])
    report.value = r
    trend.value = tr
  } catch (e) {
    showHttpFeedback(e, t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

async function doExport(format: 'pdf' | 'csv' | 'json') {
  exporting.value = true
  try {
    if (format === 'pdf') {
      const blob = await reportsApi.exportUserRiskPdf(days.value)
      triggerBlobDownload(blob, `risk-report-${days.value}d.pdf`)
    } else if (format === 'csv') {
      const blob = await reportsApi.exportUserRiskCsv(days.value)
      triggerBlobDownload(blob, `risk-report-${days.value}d.csv`)
    } else {
      const data = await reportsApi.exportUserRiskJson(days.value)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      triggerBlobDownload(blob, `risk-report-${days.value}d.json`)
    }
    ElMessage.success(t('common.exportSuccess'))
  } catch (e) {
    showHttpFeedback(e, t('common.exportFailed'))
  } finally {
    exporting.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div
    v-loading="loading"
    class="user-reports-page"
  >
    <div class="page-summary">
      <p class="page-summary__eyebrow">
        {{ t('userReports.eyebrow') }}
      </p>
      <h2>{{ t('userReports.title') }}</h2>
      <p>{{ t('userReports.lede') }}</p>
    </div>
    <el-card
      v-if="report"
      class="summary-card"
    >
      <div class="summary-row">
        <el-tag
          :type="['high', 'critical', 'severe'].includes(report.severity) ? 'danger' : 'warning'"
          size="large"
        >
          {{ t('user.riskLevel') }} {{ report.risk_level }}
        </el-tag>
        <span class="score">{{ report.risk_score.toFixed(1) }}</span>
        <el-tag>{{ t('user.trend') }}: {{ report.trend }}</el-tag>
      </div>
    </el-card>

    <el-card class="trend-card">
      <template #header>
        <div class="card-header">
          <el-radio-group
            v-model="days"
            size="small"
            @change="loadData"
          >
            <el-radio-button :value="7">
              {{ t('common.days7') }}
            </el-radio-button>
            <el-radio-button :value="30">
              {{ t('common.days30') }}
            </el-radio-button>
            <el-radio-button :value="90">
              {{ t('common.days90') }}
            </el-radio-button>
            <el-radio-button :value="365">
              {{ t('common.days365') }}
            </el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <BaseChart
        :option="trendOption"
        height="320px"
      />
    </el-card>

    <el-card class="factor-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">{{ t('userReports.factorChartTitle') }}</span>
          <span class="card-sub">{{ t('userReports.factorCount') }} {{ report?.main_factors?.length || 0 }}</span>
        </div>
      </template>
      <BaseChart
        v-if="report && report.main_factors && report.main_factors.length"
        :option="factorOption"
        height="280px"
      />
      <el-empty
        v-else
        :description="t('userReports.factorChartEmpty')"
      />
    </el-card>

    <el-card class="export-card">
      <el-button
        type="primary"
        :loading="exporting"
        @click="doExport('pdf')"
      >
        {{ t('common.exportPdf') }}
      </el-button>
      <el-button
        :loading="exporting"
        @click="doExport('csv')"
      >
        {{ t('common.csv') }}
      </el-button>
      <el-button
        :loading="exporting"
        @click="doExport('json')"
      >
        {{ t('common.json') }}
      </el-button>
    </el-card>
  </div>
</template>

<style scoped>
.user-reports-page { display: flex; flex-direction: column; gap: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.card-title { font-weight: var(--font-weight-semibold); }
.card-sub { font-size: var(--font-size-extra-small); color: var(--text-secondary); }
.page-summary {
  padding: 1rem 1.25rem;
  border: 1px solid var(--border-extra-light);
  border-radius: 1rem;
  background: var(--bg-primary);
}
.page-summary__eyebrow {
  margin: 0 0 0.35rem;
  color: var(--text-secondary);
  font-size: var(--font-size-extra-small);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.page-summary h2 { margin: 0; }
.page-summary p:last-child { margin: 0.4rem 0 0; color: var(--text-secondary); line-height: 1.6; }
.summary-row { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.score { font-size: var(--font-size-display); font-weight: 700; }
@media (max-width: 768px) { .summary-row { gap: 12px; } }
</style>

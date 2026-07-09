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

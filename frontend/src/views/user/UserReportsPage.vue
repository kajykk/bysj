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

function parseFilename(disposition: string | undefined, fallback: string): string {
  if (!disposition) return fallback
  const m = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i)
  return m ? decodeURIComponent(m[1]) : fallback
}

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
  <div v-loading="loading" class="user-reports-page">
    <el-card v-if="report" class="summary-card">
      <div class="summary-row">
        <el-tag :type="report.severity === 'high' ? 'danger' : 'warning'" size="large">
          {{ t('user.riskLevel') }} {{ report.risk_level }}
        </el-tag>
        <span class="score">{{ report.risk_score.toFixed(1) }}</span>
        <el-tag>{{ t('user.trend') }}: {{ report.trend }}</el-tag>
      </div>
    </el-card>

    <el-card class="trend-card">
      <template #header>
        <div class="card-header">
          <el-radio-group v-model="days" size="small" @change="loadData">
            <el-radio-button :value="7">7d</el-radio-button>
            <el-radio-button :value="30">30d</el-radio-button>
            <el-radio-button :value="90">90d</el-radio-button>
            <el-radio-button :value="365">365d</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <BaseChart :option="trendOption" height="320px" />
    </el-card>

    <el-card class="export-card">
      <el-button type="primary" :loading="exporting" @click="doExport('pdf')">{{ t('common.exportPdf') }}</el-button>
      <el-button :loading="exporting" @click="doExport('csv')">CSV</el-button>
      <el-button :loading="exporting" @click="doExport('json')">JSON</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.user-reports-page { display: flex; flex-direction: column; gap: 16px; }
.summary-row { display: flex; align-items: center; gap: 16px; }
.score { font-size: 28px; font-weight: 700; }
</style>

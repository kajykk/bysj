<!-- frontend/src/views/user/UserReportsPage.vue -->
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { userRiskApi } from '@/api/userRiskApi'
import { reportsApi } from '@/api/reportsApi'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { normalizeHttpError } from '@/utils/errorPolicy'
import BaseChart from '@/components/charts/BaseChart.vue'
import { CHART_SERIES_COLORS } from '@/utils/chartPalette'
import type { EChartsCoreOption } from '@/utils/echarts'
import type { RiskReport, RiskTrend } from '@/api/userRiskApi'

const { t } = useI18n()
const report = ref<RiskReport | null>(null)
const trend = ref<RiskTrend | null>(null)
const days = ref(30)
const loading = ref(false)
const exporting = ref(false)
/** FIX-2026-10-08：报告加载失败时的页面级错误态（改前失败即静默白屏）。 */
const loadError = ref('')

/**
 * FIX-2026-10-08（空值白屏）：摘要卡原本直接 `report.risk_score.toFixed(1)`。
 *
 * 后端当前确实保证非空（backend/app/models/risk.py:64 `risk_score` 为
 * `nullable=False` + `risk_score BETWEEN 0 AND 100` 约束），所以这不是「后端
 * 会返回 null」的缺陷，而是**渲染层的纵深防御**：`requestData<T>`
 * （frontend/src/api/request.ts:352-355）只是 `res.data.data` 的一次**纯类型
 * 断言**，没有任何运行时校验。契约一旦漂移（后端新增降级路径 / 网关截断 /
 * 版本不一致），模板求值就会抛 TypeError，Vue 丢弃该组件子树 —— 用户看到的是
 * 整块白屏，控制台只有一行报错。心理健康场景下「报告消失」的代价远高于
 * 「显示一个占位符」，因此这里显式兜底为 '-'。
 *
 * 边界值纪律：只有 null / undefined / NaN 才显示 '-'，0 必须照常显示 '0.0'，
 * 否则「0 分」会被误读成「没有数据」。
 */
function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return value.toFixed(1)
}

/** 风险等级同理：等级缺失时显示占位符而不是裸 null。 */
function formatLevel(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return String(value)
}

/**
 * 高严重度判定。原实现硬编码 `['high','critical','severe']`，但后端
 * `RISK_LEVEL_LABELS`（backend/app/core/risk_thresholds.py:42-48）的值域是
 * none/mild/moderate/high/critical —— `severe` 永远不可能命中，是死代码。
 */
function isHighSeverity(severity: string | null | undefined): boolean {
  return severity === 'high' || severity === 'critical'
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

// VIS-P4-01 修复：复用统一图表色板，消除硬编码 hex
const FACTOR_COLORS = CHART_SERIES_COLORS
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
  loadError.value = ''
  try {
    const [r, tr] = await Promise.all([
      userRiskApi.getRiskReport(),
      userRiskApi.getRiskTrend(days.value),
    ])
    report.value = r
    trend.value = tr
  } catch (e) {
    // FIX-2026-10-08：接口失败时 report 恒为 null，改前页面只剩标题一段文字
    // （摘要卡/因子卡全部 v-if 掉），用户看到的就是「空值白屏」且无从判断
    // 是「没有数据」还是「加载失败」。这里保留页面级错误态并给出重试入口。
    loadError.value = normalizeHttpError(e, t('common.loadFailed')).detail
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
          :type="isHighSeverity(report.severity) ? 'danger' : 'warning'"
          size="large"
        >
          {{ t('user.riskLevel') }} {{ formatLevel(report.risk_level) }}
        </el-tag>
        <span class="score">{{ formatScore(report.risk_score) }}</span>
        <el-tag>{{ t('user.trend') }}: {{ report.trend ?? '-' }}</el-tag>
      </div>
    </el-card>

    <!-- FIX-2026-10-08：报告缺失（接口失败 / 尚无数据）时给出明确空态与重试，
         改前该区域整块被 v-if 掉，用户只看到标题，等同于白屏。 -->
    <el-card
      v-else-if="!loading"
      class="summary-card"
    >
      <el-empty :description="loadError || t('common.noData')">
        <el-button
          type="primary"
          plain
          @click="loadData"
        >
          {{ t('common.retry') }}
        </el-button>
      </el-empty>
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

<template>
  <StatefulContainer
    :loading="loading"
    :empty="false"
    :error-message="error"
    @retry="emit('retry')"
  >
    <template v-if="report">
      <el-row :gutter="16">
        <el-col :span="8">
          <el-card>
            <div class="report-score-wrap">
              <el-progress
                type="dashboard"
                :percentage="report.risk_score"
                :color="scoreColor"
                :width="140"
              >
                <template #default="{ percentage }">
                  <div class="dashboard-score">
                    <span class="score-num">{{ percentage }}</span>
                    <span class="score-label">{{ t('riskReport.scoreLabel') }}</span>
                  </div>
                </template>
              </el-progress>
            </div>
            <div class="report-meta">
              <el-tag :type="severityTagType">
                {{ severityLabelText }}
              </el-tag>
              <el-tag
                v-if="report.review_required"
                type="warning"
                effect="dark"
              >
                {{ t('riskReport.needsReview') }}
              </el-tag>
              <el-tag
                v-if="report.crisis_override"
                type="danger"
                effect="dark"
              >
                {{ t('riskReport.crisisOverride') }}
              </el-tag>
              <span class="trend-text">
                {{ t('riskReport.trend') }}
                <el-icon
                  v-if="report.trend === 'up'"
                  color="#d65a5a"
                ><Top /></el-icon>
                <el-icon
                  v-else-if="report.trend === 'down'"
                  color="#5a9e3a"
                ><Bottom /></el-icon>
                <span v-else>{{ t('riskReport.trendStable') }}</span>
              </span>
            </div>
            <el-descriptions
              v-if="report.physiological_score != null || report.modality_contributions"
              :column="1"
              border
              size="small"
              style="margin-top: 12px"
            >
              <el-descriptions-item :label="t('riskReport.physioScoreLabel')">
                {{ report.physiological_score ?? t('riskReport.notAvailable') }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('riskReport.modalityContributionLabel')">
                <span v-if="report.modality_contributions">
                  {{ Object.entries(report.modality_contributions).map(([key, value]) => `${modalityLabel(key)}: ${value ?? t('riskReport.notAvailable')}`).join('；') }}
                </span>
                <span v-else>{{ t('riskReport.notAvailable') }}</span>
              </el-descriptions-item>
              <el-descriptions-item
                v-if="report.risk_factors?.length"
                :label="t('riskReport.riskFactorsLabel')"
              >
                <el-tag
                  v-for="factor in report.risk_factors"
                  :key="factor.feature"
                  type="danger"
                  size="small"
                  style="margin-right: 4px; margin-bottom: 4px"
                >
                  {{ featureLabel(factor.feature) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item
                v-if="report.protective_factors?.length"
                :label="t('riskReport.protectiveFactorsLabel')"
              >
                <el-tag
                  v-for="factor in report.protective_factors"
                  :key="factor.feature"
                  type="success"
                  size="small"
                  style="margin-right: 4px; margin-bottom: 4px"
                >
                  {{ featureLabel(factor.feature) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item
                v-if="report.review_flags?.length"
                :label="t('riskReport.reviewFlagsLabel')"
              >
                <el-tag
                  v-for="flag in report.review_flags"
                  :key="flag.feature"
                  type="warning"
                  size="small"
                  style="margin-right: 4px; margin-bottom: 4px"
                >
                  {{ flag.feature }}
                </el-tag>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>

        <el-col :span="16">
          <el-card>
            <template #header>
              <span class="card-title">{{ t('riskReport.factorsAdviceTitle') }}</span>
            </template>
            <el-table
              v-if="report.main_factors?.length"
              :data="report.main_factors"
              size="small"
              stripe
              sortable="custom"
            >
              <el-table-column
                prop="feature"
                :label="t('riskReport.factorCol')"
                min-width="140"
                sortable
              >
                <template #default="{ row }">
                  {{ featureLabel(row.feature) }}
                </template>
              </el-table-column>
              <el-table-column
                prop="importance"
                :label="t('riskReport.importanceCol')"
                width="120"
                sortable
                :sort-method="(a: ReportFactor, b: ReportFactor) => a.importance - b.importance"
              >
                <template #default="{ row }">
                  <el-progress
                    :percentage="Math.min(row.importance * 100, 100)"
                    :show-text="false"
                    :stroke-width="8"
                  />
                </template>
              </el-table-column>
              <el-table-column
                prop="direction"
                :label="t('riskReport.directionCol')"
                width="100"
              >
                <template #default="{ row }">
                  <el-tag
                    :type="getFactorDirectionTagType(row.direction)"
                    size="small"
                  >
                    {{ getFactorDirectionLabel(row.direction) }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
            <el-empty
              v-else
              :description="t('riskReport.noFactorData')"
              :image-size="60"
            />
          </el-card>
        </el-col>
      </el-row>

      <el-card style="margin-top: 16px">
        <template #header>
          <span class="card-title">{{ t('riskReport.adviceTitle') }}</span>
        </template>
        <div
          v-if="report.advice?.length"
          class="advice-cards"
        >
          <el-card
            v-for="(a, i) in report.advice"
            :key="a + '-' + i"
            shadow="hover"
            class="advice-card"
            :body-style="{ padding: '14px 16px' }"
          >
            <div class="advice-index">
              {{ Number(i) + 1 }}
            </div>
            <div class="advice-text">
              {{ a }}
            </div>
          </el-card>
        </div>
        <p
          v-else
          class="text-muted"
        >
          {{ t('riskReport.noAdvice') }}
        </p>
      </el-card>

      <el-card style="margin-top: 16px">
        <template #header>
          <div class="header-row">
            <span class="card-title">{{ t('riskReport.trendTitle') }}</span>
            <el-dropdown
              v-if="canExport"
              @command="handleExport"
            >
              <el-button
                type="primary"
                size="small"
              >
                {{ t('riskReport.exportReport') }}<el-icon class="el-icon--right">
                  <ArrowDown />
                </el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="json">
                    {{ t('riskReport.exportJson') }}
                  </el-dropdown-item>
                  <el-dropdown-item command="csv">
                    {{ t('riskReport.exportCsv') }}
                  </el-dropdown-item>
                  <el-dropdown-item command="pdf">
                    {{ t('riskReport.exportPdf') }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </template>
        <div
          ref="reportTrendRef"
          style="height: 260px"
        />
      </el-card>
    </template>
  </StatefulContainer>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ProgressColor } from 'element-plus'
import { Top, Bottom, ArrowDown } from '@element-plus/icons-vue'
import { echarts, type ECharts } from '@/utils/echarts'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import type { RiskTrend } from '@/api/modelApi'
import type { ReportFactor, RiskReport } from '@/api/userRiskApi'
import {
  featureLabel,
  modalityLabel,
  severityLabel,
  getFactorDirectionLabel,
  getFactorDirectionTagType,
  getRiskScoreColor,
  RISK_SCORE_COLORS,
} from '@/utils/riskFormatters'
import { subscribeResize } from '@/utils/sharedResize'

interface Props {
  report: RiskReport | null
  loading: boolean
  error: string
  canExport: boolean
  trendData: RiskTrend
}

const props = defineProps<Props>()
const emit = defineEmits<{
  retry: []
  export: [format: 'json' | 'csv' | 'pdf']
}>()

const { t } = useI18n()

let isUnmounted = false
const reportTrendRef = ref<HTMLElement>()
let reportTrendChart: ECharts | null = null
// R-009 修复：使用 subscribeResize 共享全局节流 resize 监听，避免独立注册
let unsubscribeReportTrendResize: (() => void) | null = null

const disposeReportTrend = () => {
  unsubscribeReportTrendResize?.()
  unsubscribeReportTrendResize = null
  reportTrendChart?.dispose()
  reportTrendChart = null
}

const severityLabelText = computed(() => {
  if (!props.report) return ''
  return severityLabel(props.report.severity)
})

const severityTagType = computed(() => {
  if (!props.report) return 'info'
  const map: Record<string, string> = { none: 'info', mild: 'success', moderate: 'warning', high: 'danger', critical: 'danger' }
  return (map[props.report.severity] || 'info') as 'info' | 'success' | 'warning' | 'danger'
})

// ISS-053 修复：复用 riskFormatters.getRiskScoreColor 与 RISK_SCORE_COLORS 色板，消除硬编码 hex
const scoreColor = computed((): string | ProgressColor[] => {
  if (!props.report) return RISK_SCORE_COLORS.low
  return getRiskScoreColor(props.report.risk_score)
})

const handleExport = (format: 'json' | 'csv' | 'pdf') => {
  emit('export', format)
}

const renderReportTrend = async () => {
  await nextTick()
  if (!reportTrendRef.value) return
  if (isUnmounted || !reportTrendRef.value) return

  if (reportTrendChart) {
    disposeReportTrend()
  }
  reportTrendChart = echarts.init(reportTrendRef.value)
  // R-009 修复：通过 subscribeResize 注册共享监听
  unsubscribeReportTrendResize = subscribeResize(() => reportTrendChart?.resize())

  const trend = props.trendData
  const points = Array.isArray(trend.points) ? trend.points : []
  const dates = points.map(p => p.date)
  const valueOrNull = (value: number | null | undefined) => typeof value === 'number' ? value : null
  const sourceLabelMap: Record<string, string> = {
    fusion: t('riskReport.sourceFusion'),
    structured: t('riskReport.sourceStructured'),
    text: t('riskReport.sourceText'),
    physiological: t('riskReport.sourcePhysiological')
  }
  const riskLevelMap: Record<number, string> = {
    0: t('riskReport.chartRiskLevel0'),
    1: t('riskReport.chartRiskLevel1'),
    2: t('riskReport.chartRiskLevel2'),
    3: t('riskReport.chartRiskLevel3'),
    4: t('riskReport.chartRiskLevel4')
  }

  reportTrendChart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params as Array<{ dataIndex: number; marker: string; seriesName: string; value: number | null }> : []
        const point = points[items[0]?.dataIndex ?? 0]
        if (!point) return ''
        const escapeHtml = (value: unknown) => {
          if (value === null || value === undefined) return ''
          return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
        }
        const safeDate = escapeHtml(point.date)
        const safeAssessmentType = escapeHtml(point.assessment_type)
        const safeRiskLevel = escapeHtml(point.risk_level)
        const safeRecordCount = escapeHtml(point.record_count ?? 1)
        const lines = [
          `<strong>${safeDate}</strong>`,
          `${t('riskReport.chartMainAssessment')}${sourceLabelMap[String(point.assessment_type || '')] || safeAssessmentType || t('riskReport.chartUnknown')}`,
          `${t('riskReport.chartRiskLevel')}${riskLevelMap[point.risk_level] || `${t('riskReport.chartLevelPrefix')}${safeRiskLevel}`}`,
          `${t('riskReport.chartDailyRecords')}${safeRecordCount} ${t('riskReport.chartRecordsUnit')}`,
        ]
        items.forEach(item => {
          if (item.value !== null && item.value !== undefined) {
            lines.push(`${item.marker}${item.seriesName}：${Number(item.value).toFixed(2)}`)
          }
        })
        return lines.join('<br/>')
      }
    },
    legend: { top: 0, data: [t('riskReport.legendComprehensive'), t('riskReport.legendStructured'), t('riskReport.legendText'), t('riskReport.legendPhysiological')], textStyle: { fontSize: 11 } },
    grid: { left: 40, right: 20, top: 42, bottom: 30 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { fontSize: 11 } },
    graphic: points.length
      ? []
      : [{
          type: 'text',
          left: 'center',
          top: 'middle',
          style: {
            text: t('riskReport.noTrendData'),
            fill: '#7a8290',
            fontSize: 14
          }
        }],
    series: [
      {
        name: t('riskReport.legendComprehensive'), type: 'line', data: points.map(p => p.risk_score), smooth: true,
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(64,158,255,0.3)' }, { offset: 1, color: 'rgba(64,158,255,0.02)' }
        ]) },
        lineStyle: { color: '#3b82c4', width: 2 }, itemStyle: { color: '#3b82c4' }
      },
      { name: t('riskReport.legendStructured'), type: 'line', data: points.map(p => valueOrNull(p.structured_score)), smooth: true, connectNulls: true, lineStyle: { color: '#5a9e3a', width: 1.8 }, itemStyle: { color: '#5a9e3a' } },
      { name: t('riskReport.legendText'), type: 'line', data: points.map(p => valueOrNull(p.text_score)), smooth: true, connectNulls: true, lineStyle: { color: '#d4923a', width: 1.8 }, itemStyle: { color: '#d4923a' } },
      { name: t('riskReport.legendPhysiological'), type: 'line', data: points.map(p => valueOrNull(p.physiological_score)), smooth: true, connectNulls: true, lineStyle: { color: '#d65a5a', width: 1.8 }, itemStyle: { color: '#d65a5a' } },
    ]
  })
}

onMounted(() => {
  renderReportTrend()
})

watch(() => props.trendData, () => {
  renderReportTrend()
})

onUnmounted(() => {
  isUnmounted = true
  disposeReportTrend()
})
</script>

<style scoped>
.report-score-wrap {
  display: flex;
  justify-content: center;
  padding: 12px 0;
}

.dashboard-score {
  text-align: center;
}

.score-num {
  font-size: 28px;
  font-weight: 700;
  display: block;
}

.score-label {
  font-size: 12px;
  color: #7a8290;
}

.report-meta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 8px;
}

.trend-text {
  font-size: 13px;
  color: #5a6470;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.advice-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.advice-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border-radius: 8px;
  transition: transform 0.2s ease;
}

.advice-card:hover {
  transform: translateX(4px);
}

.advice-index {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82c4, #4a9bd6);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.advice-text {
  font-size: 13px;
  color: #2c3340;
  line-height: 1.6;
  flex: 1;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-weight: 600;
}

.text-muted {
  color: #7a8290;
  font-size: 13px;
}
</style>

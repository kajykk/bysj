<template>
  <StatefulContainer
    :loading="loading"
    :empty="false"
    :error-message="error"
    @retry="emit('retry')"
  >
    <template v-if="report">
      <el-row :gutter="16">
        <!-- BLANK-07 修复：补充响应式断点，窄屏整行堆叠，避免 8 栅列放不下 140px 仪表盘 -->
        <el-col
          :xs="24"
          :sm="24"
          :md="8"
        >
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

        <el-col
          :xs="24"
          :sm="24"
          :md="16"
        >
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
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ProgressColor } from 'element-plus'
import { Top, Bottom, ArrowDown } from '@element-plus/icons-vue'
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
import { buildReportTrendOption } from './composables/reportTrendOption'
import { useTrendChart } from './composables/useTrendChart'

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

// R-E3: 图表生命周期与 option 构建收敛到 composable/纯函数模块
const {
  containerRef: reportTrendRef,
  render: renderReportTrend,
} = useTrendChart({
  getOption: () => buildReportTrendOption(props.trendData, t),
  deps: [() => props.trendData],
})

onMounted(() => {
  renderReportTrend()
})
</script>

<style scoped>
/* MOBILE-01 修复：窄屏下带边框 el-descriptions 的标签列被压缩、
   中文标签逐字竖排；为标签单元格保留最小宽度，保证可读性 */
:deep(.el-descriptions__label) {
  min-width: 88px;
}

.report-score-wrap {
  display: flex;
  justify-content: center;
  padding: 12px 0;
}

.dashboard-score {
  text-align: center;
}

.score-num {
  font-size: var(--font-size-display);
  font-weight: 700;
  display: block;
}

.score-label {
  font-size: var(--font-size-extra-small);
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
  font-size: var(--font-size-small);
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
  background: linear-gradient(135deg, #2e6fa8, #4a9bd6);
  color: #fff;
  font-size: var(--font-size-extra-small);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.advice-text {
  font-size: var(--font-size-small);
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
  font-size: var(--font-size-small);
}
</style>

<template>
  <div class="layout">
    <div class="layout__header">
      <div>
        <p class="layout__eyebrow">
          <span
            class="layout__eyebrow-dot breathe-dot"
            aria-hidden="true"
          />
          {{ t('userDashboard.eyebrow') }}
        </p>
        <h2>{{ t('userDashboard.title') }}</h2>
        <p>{{ t('userDashboard.welcome', { name: auth.user?.nickname || auth.user?.username || t('userDashboard.defaultUserName') }) }}</p>
      </div>
      <div class="layout__actions">
        <el-tag type="primary">
          {{ t('userDashboard.tagUserEnd') }}
        </el-tag>
        <el-button @click="handleLogout">
          {{ t('userDashboard.btnLogout') }}
        </el-button>
      </div>
    </div>

    <section class="next-step-card">
      <p class="next-step-card__label">
        {{ nextAction.label }}
      </p>
      <p class="next-step-card__title">
        {{ nextAction.title }}
      </p>
      <p class="next-step-card__desc">
        {{ nextAction.description }}
      </p>
      <div class="next-step-card__actions">
        <el-button
          type="primary"
          @click="nextAction.action()"
        >
          {{ nextAction.primaryText }}
        </el-button>
        <el-button
          link
          type="primary"
          @click="router.push(nextAction.secondaryPath)"
        >
          {{ nextAction.secondaryText }}
        </el-button>
      </div>
    </section>

    <!-- Bento 网格：风险状态主视觉（2fr）+ 副卡（1fr），打破 3 等宽卡片行 -->
    <div class="bento-grid bento-grid--top">
      <!-- 主视觉：风险状态（占据更宽列，作为 Hero 数据卡） -->
      <section class="bento-cell bento-cell--hero bento-item shimmer-sweep">
        <header class="bento-cell__head">
          <div class="bento-cell__title-group">
            <span
              class="bento-cell__live-dot breathe-dot"
              aria-hidden="true"
            />
            <h3 class="bento-cell__title">
              {{ t('userDashboard.riskStatusTitle') }}
            </h3>
          </div>
          <el-tag
            :type="severityTagType"
            size="small"
            effect="light"
            round
          >
            {{ severityLabel }}
          </el-tag>
        </header>

        <div
          v-if="riskLoading"
          class="card-loading"
        >
          <el-skeleton
            :rows="3"
            animated
          />
        </div>
        <EmptyState
          v-else-if="riskError"
          :title="t('userDashboard.loadFailed')"
          :description="riskError"
          :image-size="40"
        >
          <template #action>
            <el-button
              type="primary"
              plain
              @click="loadRiskReport"
            >
              {{ t('userDashboard.btnReload') }}
            </el-button>
          </template>
        </EmptyState>
        <template v-else>
          <div class="risk-score-display">
            <CountUp
              :end="riskReport.risk_score"
              :duration="1500"
              :suffix="t('userDashboard.scoreUnit')"
            />
          </div>
          <el-progress
            :percentage="riskReport.risk_score"
            :color="riskColor"
            :stroke-width="14"
            :text-inside="true"
            :format="(p: number) => p + t('userDashboard.scoreUnit')"
          />
          <div class="risk-meta">
            <span class="trend-label">
              {{ t('userDashboard.trendLabel') }}
              <el-icon
                v-if="riskReport.trend === 'up'"
                color="#d65a5a"
              ><Top /></el-icon>
              <el-icon
                v-else-if="riskReport.trend === 'down'"
                color="#5a9e3a"
              ><Bottom /></el-icon>
              <span v-else>{{ t('userDashboard.trendStable') }}</span>
            </span>
          </div>
          <p class="risk-advice">
            <!-- ISS-092 TODO：风险说明目前仅显示 advice 第一条文案，后续可补充可展开的"风险因子与保护因素"详细说明 -->
            {{ riskReport.advice?.[0] || t('userDashboard.riskAdviceFallback') }}
          </p>
        </template>
      </section>

      <!-- 副卡列：最近测评 + 干预计划垂直堆叠 -->
      <div class="bento-cell-stack">
        <section class="bento-cell bento-item shimmer-sweep">
          <header class="bento-cell__head">
            <h3 class="bento-cell__title">
              {{ t('userDashboard.latestAssessmentTitle') }}
            </h3>
          </header>
          <div
            v-if="assessmentLoading"
            class="card-loading"
          >
            <el-skeleton
              :rows="2"
              animated
            />
          </div>
          <EmptyState
            v-else-if="assessmentError"
            :title="t('userDashboard.loadFailed')"
            :description="assessmentError"
            :image-size="40"
          >
            <template #action>
              <el-button
                type="primary"
                plain
                @click="loadLatestAssessment"
              >
                {{ t('userDashboard.btnReload') }}
              </el-button>
            </template>
          </EmptyState>
          <template v-else-if="latestAssessment">
            <div class="stat-row">
              <span class="stat-label">{{ t('userDashboard.assessmentTypeLabel') }}</span>
              <el-tag size="small">
                {{ assessmentTypeLabel(getAssessmentType(latestAssessment)) }}
              </el-tag>
            </div>
            <div class="stat-row">
              <span class="stat-label">{{ t('userDashboard.assessmentTimeLabel') }}</span>
              <span class="stat-value tabular-nums">{{ formatDate(latestAssessment.created_at, 'MM/DD HH:mm') }}</span>
            </div>
            <el-button
              type="primary"
              plain
              class="cell-action"
              @click="router.push('/user/risk')"
            >
              {{ t('userDashboard.btnStartAssessment') }}
            </el-button>
          </template>
          <template v-else>
            <EmptyState
              :title="t('userDashboard.emptyNoRecord')"
              :description="t('userDashboard.emptyNoRecordDesc')"
              :image-size="40"
            >
              <template #action>
                <el-button
                  type="primary"
                  plain
                  @click="router.push('/user/risk')"
                >
                  {{ t('userDashboard.btnStartAssessment') }}
                </el-button>
              </template>
            </EmptyState>
          </template>
        </section>

        <section class="bento-cell bento-item shimmer-sweep">
          <header class="bento-cell__head">
            <h3 class="bento-cell__title">
              {{ t('userDashboard.interventionPlanTitle') }}
            </h3>
          </header>
          <div
            v-if="interventionLoading"
            class="card-loading"
          >
            <el-skeleton
              :rows="2"
              animated
            />
          </div>
          <EmptyState
            v-else-if="interventionError"
            :title="t('userDashboard.loadFailed')"
            :description="interventionError"
            :image-size="40"
          >
            <template #action>
              <el-button
                type="primary"
                plain
                @click="loadActiveIntervention"
              >
                {{ t('userDashboard.btnReload') }}
              </el-button>
            </template>
          </EmptyState>
          <template v-else-if="activeIntervention.plan.id">
            <div class="stat-row">
              <span class="stat-label">{{ t('userDashboard.planNameLabel') }}</span>
              <span class="stat-value">{{ activeIntervention.plan.plan_name }}</span>
            </div>
            <el-progress
              :percentage="activeIntervention.plan.progress"
              :stroke-width="10"
              class="intervention-progress"
            />
            <div class="stat-row">
              <span class="stat-label">{{ t('userDashboard.todayTasksLabel') }}</span>
              <span class="stat-value tabular-nums">{{ completedTasks }}/{{ activeIntervention.tasks.length }}</span>
            </div>
            <el-button
              type="primary"
              plain
              class="cell-action"
              @click="router.push('/user/intervention')"
            >
              {{ t('userDashboard.btnViewDetail') }}
            </el-button>
          </template>
          <template v-else>
            <EmptyState
              :title="t('userDashboard.emptyNoActivePlan')"
              :description="t('userDashboard.emptyNoActivePlanDesc')"
              :image-size="40"
            >
              <template #action>
                <el-button
                  type="primary"
                  plain
                  @click="router.push('/user/risk')"
                >
                  {{ t('userDashboard.btnAssessFirst') }}
                </el-button>
              </template>
            </EmptyState>
          </template>
        </section>
      </div>
    </div>

    <!-- 第二行：风险趋势（宽）+ 未读预警（窄） -->
    <div class="bento-grid bento-grid--bottom">
      <section class="bento-cell bento-item">
        <header class="bento-cell__head bento-cell__head--split">
          <h3 class="bento-cell__title">
            {{ t('userDashboard.riskTrendTitle') }}
          </h3>
          <el-radio-group
            v-model="trendDays"
            size="small"
            @change="handleTrendDaysChange"
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
          v-if="trendLoading"
          class="card-loading"
        >
          <el-skeleton
            :rows="4"
            animated
          />
        </div>
        <EmptyState
          v-else-if="trendError"
          :title="t('userDashboard.loadFailed')"
          :description="trendError"
          :image-size="60"
        >
          <template #action>
            <el-button
              type="primary"
              plain
              @click="loadRiskTrend"
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

      <section class="bento-cell bento-item">
        <header class="bento-cell__head">
          <div class="bento-cell__title-group">
            <span
              v-if="unreadWarnings.length > 0"
              class="bento-cell__live-dot bento-cell__live-dot--alert breathe-dot"
              aria-hidden="true"
            />
            <h3 class="bento-cell__title">
              {{ t('userDashboard.unreadWarningsTitle') }}
            </h3>
          </div>
          <span
            v-if="unreadWarnings.length > 0"
            class="warning-count tabular-nums"
          >{{ unreadWarnings.length }}</span>
        </header>
        <div
          v-if="warningLoading"
          class="card-loading"
        >
          <el-skeleton
            :rows="3"
            animated
          />
        </div>
        <EmptyState
          v-else-if="warningError"
          :title="t('userDashboard.loadFailed')"
          :description="warningError"
          :image-size="60"
        >
          <template #action>
            <el-button
              type="primary"
              plain
              @click="loadWarnings"
            >
              {{ t('userDashboard.btnReload') }}
            </el-button>
          </template>
        </EmptyState>
        <template v-else-if="unreadWarnings.length > 0">
          <ul class="warning-list">
            <li
              v-for="w in unreadWarnings.slice(0, 5)"
              :key="w.id"
              class="warning-item"
            >
              <el-tag
                :type="w.risk_level >= 3 ? 'danger' : w.risk_level === 2 ? 'warning' : 'info'"
                size="small"
                effect="light"
              >
                {{ w.risk_level >= 3 ? t('userDashboard.warningHigh') : w.risk_level === 2 ? t('userDashboard.warningMedium') : t('userDashboard.warningLow') }}
              </el-tag>
              <span class="warning-title">{{ w.title }}</span>
              <span class="warning-time tabular-nums">{{ formatDate(w.created_at, 'MM/DD HH:mm') }}</span>
            </li>
          </ul>
          <el-button
            type="primary"
            link
            class="cell-action"
            @click="router.push('/user/warnings')"
          >
            {{ t('userDashboard.btnViewAll') }}
          </el-button>
        </template>
        <EmptyState
          v-else
          :title="t('userDashboard.emptyNoUnread')"
          :description="t('userDashboard.emptyNoUnreadDesc')"
          :image-size="60"
        />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Top, Bottom } from '@element-plus/icons-vue'
import { echarts, type ECharts } from '@/utils/echarts'
import { useAuthStore } from '@/stores/auth'
import { userApi } from '@/api/userApi'
import EmptyState from '@/components/common/EmptyState.vue'
import CountUp from '@/components/common/CountUp.vue'
import type { ActiveIntervention, RiskReport, RiskTrend } from '@/api/userRiskApi'
import type { WarningItem, DataHistoryItem } from '@/api/userTypes'
// P2-D 修复：复用 riskFormatters 的 getRiskScoreColor，消除魔法数字
import { getRiskScoreColor } from '@/utils/riskFormatters'
import { formatDate } from '@/utils/formatUtils'
import { subscribeResize } from '@/utils/sharedResize'

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()

// 防止组件卸载后异步请求返回仍赋值 ref
let isUnmounted = false

// ISS-077 修复：从 CSS 变量读取图表色板，消除 echarts 配置中的硬编码 hex
const readChartVar = (name: string, fallback: string): string => {
  if (typeof window === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

const riskReport = ref<RiskReport>({
  risk_level: 0,
  risk_score: 0,
  severity: 'none',
  trend: 'stable',
  main_factors: [],
  advice: [],
  assessed_at: null
})
const riskLoading = ref(true)
const riskError = ref('')

const activeIntervention = ref<ActiveIntervention>({
  plan: { id: null, plan_name: '', risk_level: 0, start_date: null, progress: 0 },
  tasks: []
})
const interventionLoading = ref(true)
const interventionError = ref('')

const riskTrend = ref<RiskTrend>({ days: 30, direction: 'stable', points: [] })
const trendLoading = ref(true)
const trendError = ref('')
const trendDays = ref(30)
const trendChartRef = ref<HTMLElement>()
let trendChart: ECharts | null = null
// R-009 修复：使用 subscribeResize 共享全局节流 resize 监听，避免独立注册
let unsubscribeTrendResize: (() => void) | null = null

const handleTrendDaysChange = async () => {
  await loadRiskTrend()
}

const disposeTrendChart = () => {
  unsubscribeTrendResize?.()
  unsubscribeTrendResize = null
  trendChart?.dispose()
  trendChart = null
}

const unreadWarnings = ref<WarningItem[]>([])
const warningLoading = ref(true)
const warningError = ref('')

const latestAssessment = ref<DataHistoryItem | null>(null)
const assessmentLoading = ref(true)
const assessmentError = ref('')

const completedTasks = computed(() => activeIntervention.value.tasks.filter((task) => task.today_status === 'completed').length)

const nextAction = computed(() => {
  if (riskLoading.value || interventionLoading.value || warningLoading.value || assessmentLoading.value) {
    return {
      label: t('userDashboard.nextActionLabelFallback'),
      title: t('userDashboard.nextActionTitleFallback'),
      description: t('userDashboard.nextActionDescFallback'),
      primaryText: t('userDashboard.btnReload'),
      secondaryText: t('userDashboard.btnViewAll'),
      secondaryPath: '/user/warnings',
      action: () => loadDashboard(),
    }
  }
  if (!latestAssessment.value) {
    return {
      label: t('userDashboard.nextActionLabelAssessment'),
      title: t('userDashboard.nextActionTitleAssessment'),
      description: t('userDashboard.nextActionDescAssessment'),
      primaryText: t('userDashboard.btnStartAssessment'),
      secondaryText: t('userDashboard.btnViewAll'),
      secondaryPath: '/user/reports',
      action: () => router.push('/user/risk'),
    }
  }
  if (riskReport.value.risk_score >= 70 || activeIntervention.value.plan.id) {
    return {
      label: t('userDashboard.nextActionLabelIntervention'),
      title: t('userDashboard.nextActionTitleIntervention'),
      description: t('userDashboard.nextActionDescIntervention'),
      primaryText: t('userDashboard.btnViewDetail'),
      secondaryText: t('userDashboard.btnViewAll'),
      secondaryPath: '/user/warnings',
      action: () => router.push('/user/intervention'),
    }
  }
  if (unreadWarnings.value.length > 0) {
    return {
      label: t('userDashboard.nextActionLabelWarnings'),
      title: t('userDashboard.nextActionTitleWarnings'),
      description: t('userDashboard.nextActionDescWarnings'),
      primaryText: t('userDashboard.btnViewAll'),
      secondaryText: t('userDashboard.btnStartAssessment'),
      secondaryPath: '/user/risk',
      action: () => router.push('/user/warnings'),
    }
  }
  return {
    label: t('userDashboard.nextActionLabelReview'),
    title: t('userDashboard.nextActionTitleReview'),
    description: t('userDashboard.nextActionDescReview'),
    primaryText: t('userDashboard.btnViewAll'),
    secondaryText: t('userDashboard.btnStartAssessment'),
    secondaryPath: '/user/risk',
    action: () => router.push('/user/reports'),
  }
})

const riskColor = computed(() => getRiskScoreColor(riskReport.value.risk_score))

const SEVERITY_LABEL_KEYS: Record<string, string> = {
  none: 'severityNone',
  mild: 'severityMild',
  moderate: 'severityModerate',
  high: 'severityHigh',
  critical: 'severityCritical',
  unknown: 'severityUnknown'
}
const severityLabel = computed(() => {
  const key = SEVERITY_LABEL_KEYS[riskReport.value.severity]
  return key ? t(`userDashboard.${key}`) : riskReport.value.severity
})

const severityTagType = computed(() => {
  const map: Record<string, string> = { none: 'info', mild: 'success', moderate: 'warning', high: 'danger', critical: 'danger' }
  return (map[riskReport.value.severity] || 'info') as 'info' | 'success' | 'warning' | 'danger'
})

const ASSESSMENT_TYPE_LABEL_KEYS: Record<string, string> = {
  structured: 'assessmentStructured',
  text: 'assessmentText',
  physiological: 'assessmentPhysiological',
  physio: 'assessmentPhysio',
  record: 'assessmentRecord'
}
const assessmentTypeLabel = (value: string | null | undefined) => {
  const key = ASSESSMENT_TYPE_LABEL_KEYS[value || '']
  return key ? t(`userDashboard.${key}`) : t('userDashboard.assessmentUnknown')
}

const getAssessmentType = (item: DataHistoryItem | null) => {
  return (item?.data as { assessment_type?: string } | undefined)?.assessment_type
}

const escapeHtml = (value: unknown) => {
  if (value === null || value === undefined) return ''
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const loadRiskReport = async () => {
  riskLoading.value = true
  riskError.value = ''
  try {
    const data = await userApi.getRiskReport()
    if (isUnmounted) return
    riskReport.value = data
  } catch {
    if (!isUnmounted) riskError.value = t('userDashboard.loadRiskFailed')
  } finally {
    if (!isUnmounted) riskLoading.value = false
  }
}

const loadActiveIntervention = async () => {
  interventionLoading.value = true
  interventionError.value = ''
  try {
    const data = await userApi.getActiveIntervention()
    if (isUnmounted) return
    activeIntervention.value = data
  } catch {
    if (!isUnmounted) interventionError.value = t('userDashboard.loadInterventionFailed')
  } finally {
    if (!isUnmounted) interventionLoading.value = false
  }
}

const loadRiskTrend = async () => {
  trendLoading.value = true
  trendError.value = ''
  try {
    const data = await userApi.getRiskTrend(trendDays.value)
    if (isUnmounted) return
    riskTrend.value = data
  } catch {
    if (!isUnmounted) trendError.value = t('userDashboard.loadTrendFailed')
  } finally {
    if (!isUnmounted) trendLoading.value = false
    await nextTick()
    if (!isUnmounted && riskTrend.value.points.length > 0 && !trendError.value) {
      renderTrendChart()
    } else if (!isUnmounted) {
      disposeTrendChart()
    }
  }
}

const loadWarnings = async () => {
  warningLoading.value = true
  warningError.value = ''
  try {
    const data = await userApi.getUserWarnings({ page: 1, page_size: 10, is_read: false })
    if (isUnmounted) return
    unreadWarnings.value = data.items
  } catch {
    if (!isUnmounted) warningError.value = t('userDashboard.loadWarningsFailed')
  } finally {
    if (!isUnmounted) warningLoading.value = false
  }
}

const loadLatestAssessment = async () => {
  assessmentLoading.value = true
  assessmentError.value = ''
  try {
    const data = await userApi.getDataHistory({ page: 1, page_size: 1 })
    if (isUnmounted) return
    latestAssessment.value = data.items[0] || null
  } catch {
    if (!isUnmounted) assessmentError.value = t('userDashboard.loadAssessmentFailed')
  } finally {
    if (!isUnmounted) assessmentLoading.value = false
  }
}

const loadDashboard = async () => {
  await Promise.allSettled([
    loadRiskReport(),
    loadActiveIntervention(),
    loadRiskTrend(),
    loadWarnings(),
    loadLatestAssessment()
  ])
  const errors = [riskError.value, interventionError.value, trendError.value, warningError.value, assessmentError.value].filter(Boolean)
  if (errors.length > 0) {
    ElMessage.warning(t('userDashboard.dashboardPartialError'))
  }
}


const CHART_RISK_LEVEL_KEYS: Record<number, string> = {
  0: 'chartRiskLevel0',
  1: 'chartRiskLevel1',
  2: 'chartRiskLevel2',
  3: 'chartRiskLevel3',
  4: 'chartRiskLevel4'
}
const CHART_TREND_KEYS: Record<string, string> = {
  up: 'chartTrendUp',
  down: 'chartTrendDown',
  stable: 'trendStable'
}

const renderTrendChart = () => {
  if (!trendChartRef.value) return
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value)
    // R-009 修复：通过 subscribeResize 注册共享监听
    unsubscribeTrendResize = subscribeResize(() => trendChart?.resize())
  }
  const points = riskTrend.value.points

  // ISS-077 修复：图表配色读取 CSS 变量令牌，与 variables.scss 统一
  const chartDanger = readChartVar('--chart-color-danger', '#d65a5a')
  const chartTextPrimary = readChartVar('--text-primary', '#2c3340')
  const chartTextSecondary = readChartVar('--text-secondary', '#8a929e')

  trendChart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#dce1e7',
      borderWidth: 1,
      textStyle: { color: chartTextPrimary, fontSize: 13 },
      extraCssText: 'box-shadow: 0 4px 16px rgba(59, 130, 196, 0.08); border-radius: 8px;',
      formatter: (params: unknown) => {
        const p = (params as Array<{ dataIndex: number }>)[0]
        const point = points[p.dataIndex]
        if (!point) return ''
        const levelKey = CHART_RISK_LEVEL_KEYS[point.risk_level]
        const levelText = levelKey ? t(`userDashboard.${levelKey}`) : t('userDashboard.severityUnknown')
        const trendKey = CHART_TREND_KEYS[riskTrend.value.direction]
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

const handleLogout = async () => {
  try {
    await ElMessageBox.confirm(t('userDashboard.logoutConfirm'), t('common.info'), { type: 'warning' })
  } catch {
    return
  }
  await auth.logout()
  await router.push('/login')
}

onMounted(() => {
  loadDashboard()
})

onUnmounted(() => {
  isUnmounted = true
  disposeTrendChart()
})
</script>

<style scoped>
.layout {
  padding: var(--spacing-xl);
  max-width: var(--layout-content-max-width);
  margin: 0 auto;
}

/* ===== 头部 ===== */
.layout__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: var(--spacing-2xl);
  gap: var(--spacing-lg);
}

.layout__eyebrow {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 0.375rem;
  font-family: var(--font-family-mono);
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.layout__eyebrow-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary-color);
  box-shadow: 0 0 8px rgba(59, 130, 196, 0.6);
}

.layout__header h2 {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: 1.875rem;
  font-weight: 600;
  letter-spacing: -0.025em;
  line-height: 1.15;
  color: var(--text-primary);
}

.layout__header p {
  margin: 0.375rem 0 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: var(--line-height-normal);
}

.layout__actions {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
  flex-shrink: 0;
}

.next-step-card {
  margin-top: var(--spacing-md);
  padding: 1rem 1.1rem;
  border: 1px solid var(--border-extra-light);
  border-radius: 1rem;
  background: var(--bg-primary);
  box-shadow: 0 1px 2px rgba(15, 22, 32, 0.04);
}

.next-step-card__label {
  margin: 0 0 0.35rem;
  font-size: var(--font-size-extra-small);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.next-step-card__title {
  margin: 0;
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.next-step-card__desc {
  margin: 0.35rem 0 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: 1.6;
}

.next-step-card__actions {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
  margin-top: 0.75rem;
}

/* ===== Bento 网格（非对称：2fr 1fr，规则 6：DESIGN_VARIANCE=8） ===== */
.bento-grid--top {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.bento-grid--bottom {
  display: grid;
  grid-template-columns: 1.85fr 1fr;
  gap: var(--spacing-lg);
}

.bento-cell-stack {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: var(--spacing-lg);
}

/* Bento 单元：替代通用 el-card，使用纯净白底 + 1px 边框 + 扩散阴影（规则 9-A） */
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
  box-shadow: 0 12px 32px -12px rgba(59, 130, 196, 0.14);
  border-color: var(--border-light);
}

.bento-cell--hero {
  background:
    linear-gradient(180deg, rgba(59, 130, 196, 0.025) 0%, transparent 60%),
    var(--bg-primary);
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

.bento-cell__title-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.bento-cell__title {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: 0.9375rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.bento-cell__live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--primary-color);
  box-shadow: 0 0 8px rgba(59, 130, 196, 0.6);
  flex-shrink: 0;
}

.bento-cell__live-dot--alert {
  background: var(--danger-color);
  box-shadow: 0 0 8px rgba(214, 90, 90, 0.6);
}

.warning-count {
  font-family: var(--font-family-mono);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--danger-color);
  background: var(--danger-light);
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  min-width: 1.5rem;
  text-align: center;
}

.card-loading {
  padding: var(--spacing-lg) 0;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.stat-label {
  font-size: var(--font-size-small);
  color: var(--text-regular);
}

.stat-value {
  font-size: var(--font-size-small);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

/* 风险分数主视觉（Hero 卡内） */
.risk-score-display {
  font-family: var(--font-family-display);
  font-size: 3.5rem;
  font-weight: 700;
  letter-spacing: -0.04em;
  color: var(--text-primary);
  margin: 0.5rem 0 1rem;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.risk-score-display :deep(.count-up-number) {
  font-family: var(--font-family-display);
}

.risk-meta {
  display: flex;
  align-items: center;
  margin-top: var(--spacing-md);
}

.trend-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.risk-advice {
  font-size: var(--font-size-extra-small);
  color: var(--text-regular);
  margin-top: var(--spacing-md);
  line-height: 1.6;
  padding: 0.625rem 0.875rem;
  background: var(--bg-hover);
  border-radius: 0.625rem;
  border-left: 2px solid var(--primary-color);
}

.intervention-progress {
  margin: var(--spacing-sm) 0;
}

.cell-action {
  margin-top: auto;
  align-self: flex-start;
  padding-top: 0.75rem;
}

/* 未读预警列表 */
.warning-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.warning-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 0.625rem 0;
  border-bottom: 1px solid var(--border-extra-light);
  transition: background var(--transition-fast) var(--transition-timing);
}

.warning-item:last-child {
  border-bottom: none;
}

.warning-item:hover {
  background: var(--bg-hover);
}

.warning-title {
  flex: 1;
  font-size: var(--font-size-small);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
}

.warning-time {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  font-family: var(--font-family-mono);
}

.trend-chart {
  height: 300px;
  width: 100%;
}

/* ===== 响应式：移动端强制单列（规则 6：MOBILE OVERRIDE） ===== */
@media (max-width: 1024px) {
  .bento-grid--top,
  .bento-grid--bottom {
    grid-template-columns: 1fr;
  }

  .bento-cell-stack {
    grid-template-rows: auto auto;
  }
}

@media (max-width: 768px) {
  .layout {
    padding: var(--spacing-md);
  }

  .layout__header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }

  .risk-score-display {
    font-size: 2.75rem;
  }
}
</style>

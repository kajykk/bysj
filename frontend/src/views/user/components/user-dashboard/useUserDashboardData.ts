/**
 * UserDashboard 数据加载与状态管理 composable。
 * 从原 UserDashboard.vue 提取所有响应式状态、加载函数与派生计算属性，
 * 趋势图表渲染逻辑下沉至 RiskTrendChart 子组件。
 */
import { computed, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { userApi } from '@/api/userApi'
import { getRiskScoreColor } from '@/utils/riskFormatters'
import type { ActiveIntervention, RiskReport, RiskTrend } from '@/api/userRiskApi'
import type { WarningItem, DataHistoryItem } from '@/api/userTypes'
import {
  SEVERITY_LABEL_KEYS,
  SEVERITY_TAG_TYPE_MAP,
  ASSESSMENT_TYPE_LABEL_KEYS,
  getAssessmentType,
  type NextAction
} from './sharedDashboardUtils'

/** 最近活动时间线条目 */
export interface ActivityItem {
  id: string
  type: 'assessment' | 'warning' | 'plan'
  title: string
  time: string
  color: string
}

export function useUserDashboardData() {
  const { t } = useI18n()
  const router = useRouter()

  // 防止组件卸载后异步请求返回仍赋值 ref
  let isUnmounted = false

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

  const unreadWarnings = ref<WarningItem[]>([])
  const warningLoading = ref(true)
  const warningError = ref('')

  const latestAssessment = ref<DataHistoryItem | null>(null)
  const assessmentLoading = ref(true)
  const assessmentError = ref('')

  const completedTasks = computed(() =>
    activeIntervention.value.tasks.filter((task) => task.today_status === 'completed').length
  )

  const riskColor = computed(() => getRiskScoreColor(riskReport.value.risk_score))

  const severityLabel = computed(() => {
    const key = SEVERITY_LABEL_KEYS[riskReport.value.severity]
    return key ? t(`userDashboard.${key}`) : riskReport.value.severity
  })

  const severityTagType = computed(() =>
    SEVERITY_TAG_TYPE_MAP[riskReport.value.severity] || 'info'
  )

  const assessmentTypeLabel = (value: string | null | undefined) => {
    const key = ASSESSMENT_TYPE_LABEL_KEYS[value || '']
    return key ? t(`userDashboard.${key}`) : t('userDashboard.assessmentUnknown')
  }

  const assessmentTypeLabelText = computed(() =>
    assessmentTypeLabel(getAssessmentType(latestAssessment.value))
  )

  // 最近活动：复用已加载的带时间戳数据，避免额外请求与虚构内容
  const activityLoading = computed(() =>
    assessmentLoading.value || warningLoading.value || interventionLoading.value
  )

  const activities = computed<ActivityItem[]>(() => {
    const items: ActivityItem[] = []

    if (latestAssessment.value?.created_at) {
      items.push({
        id: `assessment-${latestAssessment.value.id}`,
        type: 'assessment',
        title: t('userDashboard.activity.assessment'),
        time: latestAssessment.value.created_at,
        color: 'var(--primary-color)'
      })
    }

    for (const w of unreadWarnings.value) {
      if (!w.created_at) continue
      const level = w.risk_level
      const color =
        level >= 3 ? 'var(--danger-color)'
          : level === 2 ? 'var(--warning-color)'
            : 'var(--success-color)'
      items.push({
        id: `warning-${w.id}`,
        type: 'warning',
        title: t('userDashboard.activity.warning'),
        time: w.created_at,
        color
      })
    }

    const plan = activeIntervention.value.plan
    if (plan.id && plan.start_date) {
      items.push({
        id: `plan-${plan.id}`,
        type: 'plan',
        title: t('userDashboard.activity.planStarted', {
          name: plan.plan_name || t('userDashboard.defaultPlanName')
        }),
        time: plan.start_date,
        color: 'var(--success-color)'
      })
    }

    items.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
    return items.slice(0, 6)
  })

  const nextAction = computed<NextAction>(() => {
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

  onUnmounted(() => {
    isUnmounted = true
  })

  return {
    riskReport, riskLoading, riskError,
    activeIntervention, interventionLoading, interventionError,
    riskTrend, trendLoading, trendError, trendDays,
    unreadWarnings, warningLoading, warningError,
    latestAssessment, assessmentLoading, assessmentError,
    completedTasks, riskColor, severityLabel, severityTagType,
    assessmentTypeLabelText,
    activities, activityLoading,
    nextAction,
    loadRiskReport, loadActiveIntervention, loadRiskTrend, loadWarnings, loadLatestAssessment, loadDashboard
  }
}

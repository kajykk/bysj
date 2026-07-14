/**
 * AdminDashboard 数据加载与状态管理 composable。
 * 从原 AdminDashboard.vue 提取所有响应式状态、统计计算与加载逻辑，
 * 卡片渲染下沉至 StatCardsSection 子组件，系统状态/快捷操作下沉至对应子组件。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { adminApi } from '@/api/adminApi'
import {
  COMPONENT_NAME_KEYS,
  calcTrend,
  type ComponentStatusItem,
  type StatCard,
} from './sharedAdminDashboardUtils'

export function useAdminDashboardData() {
  const { t } = useI18n()
  const router = useRouter()

  const statsLoading = ref(true)
  const healthLoading = ref(true)
  const systemHealthy = ref(true)
  const stats = reactive({
    total_users: 0,
    total_counselors: 0,
    today_warnings: 0,
    today_unhandled_warnings: 0,
    total_assessments: 0,
    high_risk_users: 0,
    total_templates: 0,
    active_templates: 0,
    yesterday_users: 0,
    yesterday_warnings: 0,
    yesterday_assessments: 0,
    yesterday_templates: 0,
  })

  const userTrend = computed(() => calcTrend(stats.total_users, stats.yesterday_users))
  const warningTrend = computed(() => calcTrend(stats.today_warnings, stats.yesterday_warnings))
  const assessmentTrend = computed(() => calcTrend(stats.total_assessments, stats.yesterday_assessments))
  const templateTrend = computed(() => calcTrend(stats.active_templates, stats.yesterday_templates))

  const statCards = computed<StatCard[]>(() => [
    {
      key: 'users',
      label: t('adminDashboard.statLabelUsers'),
      value: stats.total_users,
      tone: 'primary',
      trend: userTrend.value,
      trendType: userTrend.value >= 0 ? 'success' : 'danger',
      sub: t('adminDashboard.statSubUsers', { count: stats.total_counselors }),
    },
    {
      key: 'warnings',
      label: t('adminDashboard.statLabelWarnings'),
      value: stats.today_warnings,
      tone: 'warning',
      trend: warningTrend.value,
      trendType: warningTrend.value <= 0 ? 'success' : 'danger',
      sub: t('adminDashboard.statSubWarnings', { count: stats.today_unhandled_warnings }),
      action: () => router.push('/admin/operation-logs'),
      actionText: t('adminDashboard.actionWarnings'),
      actionType: 'warning',
    },
    {
      key: 'assessments',
      label: t('adminDashboard.statLabelAssessments'),
      value: stats.total_assessments,
      tone: 'danger',
      trend: assessmentTrend.value,
      trendType: assessmentTrend.value >= 0 ? 'success' : 'danger',
      sub: t('adminDashboard.statSubAssessments', { count: stats.high_risk_users }),
    },
    {
      key: 'templates',
      label: t('adminDashboard.statLabelTemplates'),
      value: `${stats.active_templates}/${stats.total_templates}`,
      tone: 'success',
      trend: templateTrend.value,
      trendType: templateTrend.value >= 0 ? 'success' : 'danger',
      sub: '',
      action: () => router.push('/admin/templates'),
      actionText: t('adminDashboard.actionTemplates'),
      actionType: 'success',
    },
  ])

  // Bento 拆分：主指标（注册用户）单独成 Hero 卡，其余 3 项进入副指标网格
  const primaryStat = computed<StatCard>(() => statCards.value[0])
  const secondaryStats = computed<StatCard[]>(() => statCards.value.slice(1))

  const componentStatus = ref<ComponentStatusItem[]>(
    Object.keys(COMPONENT_NAME_KEYS).map((key) => ({ key, healthy: true }))
  )

  const loadStats = async () => {
    statsLoading.value = true
    try {
      const data = await adminApi.getAdminStats()
      Object.assign(stats, data)
    } catch {
      // keep defaults
    } finally {
      statsLoading.value = false
    }
  }

  const checkHealth = async () => {
    healthLoading.value = true
    try {
      const data = await adminApi.getHealthStatus()
      systemHealthy.value = data.status === 'ok'
      const checks = data.checks || {}
      // /health 接口返回的 checks 字段映射到组件状态；
      // API 服务能否拿到响应即代表其健康；文件存储不在 /health 检查范围内，保持默认健康
      componentStatus.value = componentStatus.value.map((comp) => {
        if (comp.key === 'api' || comp.key === 'storage') return comp
        return { ...comp, healthy: checks[comp.key] === 'ok' }
      })
    } catch {
      systemHealthy.value = false
      componentStatus.value = componentStatus.value.map((comp) => ({ ...comp, healthy: false }))
    } finally {
      healthLoading.value = false
    }
  }

  onMounted(() => {
    loadStats()
    checkHealth()
  })

  return {
    statsLoading, healthLoading, systemHealthy,
    primaryStat, secondaryStats, componentStatus,
    loadStats, checkHealth,
  }
}

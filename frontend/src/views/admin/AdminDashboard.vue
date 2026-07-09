<template>
  <div class="layout">
    <div class="layout__header">
      <div>
        <p class="layout__eyebrow">
          <span
            class="layout__eyebrow-dot breathe-dot"
            aria-hidden="true"
          />
          {{ t('adminDashboard.eyebrow') }}
        </p>
        <h2>{{ t('adminDashboard.title') }}</h2>
        <p>{{ t('adminDashboard.lede') }}</p>
      </div>
      <div class="layout__actions">
        <el-tag type="danger">
          {{ t('adminDashboard.tagAdmin') }}
        </el-tag>
        <el-button @click="handleLogout">
          {{ t('adminDashboard.btnLogout') }}
        </el-button>
      </div>
    </div>

    <!-- Bento 统计区：主指标卡（注册用户）+ 副指标 2x2 网格 -->
    <div class="bento-stats">
      <!-- 主指标卡：注册用户（Hero stat） -->
      <section class="bento-stat bento-stat--hero bento-item shimmer-sweep">
        <div class="stat-label">
          {{ primaryStat.label }}
        </div>
        <div
          v-if="statsLoading"
          class="stat-loading"
        >
          <el-skeleton
            :rows="1"
            animated
          />
        </div>
        <div
          v-else
          class="stat stat--hero tabular-nums"
        >
          {{ primaryStat.value }}
        </div>
        <div class="stat-trend">
          <el-tag
            :type="primaryStat.trendType"
            size="small"
            effect="plain"
          >
            <el-icon>
              <ArrowUp v-if="primaryStat.trend >= 0" />
              <ArrowDown v-else />
            </el-icon>
            {{ Math.abs(primaryStat.trend) }}%
          </el-tag>
          <span class="trend-label">{{ t('adminDashboard.trendDayOverDay') }}</span>
        </div>
        <span class="stat-sub">{{ primaryStat.sub }}</span>
      </section>

      <!-- 副指标 2x2 网格 -->
      <div class="bento-stat-grid">
        <section
          v-for="card in secondaryStats"
          :key="card.key"
          class="bento-stat bento-item shimmer-sweep"
        >
          <div class="stat-label">
            {{ card.label }}
          </div>
          <div
            v-if="statsLoading"
            class="stat-loading"
          >
            <el-skeleton
              :rows="1"
              animated
            />
          </div>
          <div
            v-else
            class="stat tabular-nums"
            :class="`stat--${card.tone}`"
          >
            {{ card.value }}
          </div>
          <div class="stat-trend">
            <el-tag
              :type="card.trendType"
              size="small"
              effect="plain"
            >
              <el-icon>
                <ArrowUp v-if="card.trend >= 0" />
                <ArrowDown v-else />
              </el-icon>
              {{ Math.abs(card.trend) }}%
            </el-tag>
            <span class="trend-label">{{ t('adminDashboard.trend') }}</span>
          </div>
          <span class="stat-sub">{{ card.sub }}</span>
          <el-button
            v-if="card.action"
            :type="card.actionType"
            link
            class="stat-action"
            @click="card.action"
          >
            {{ card.actionText }}
          </el-button>
        </section>
      </div>
    </div>

    <section class="executive-summary">
      <h3>{{ executiveSummary.title }}</h3>
      <p>{{ executiveSummary.body }}</p>
    </section>

    <!-- 第二行：系统状态（宽，Live Status）+ 快捷操作（窄） -->
    <div class="bento-grid bento-grid--bottom">
      <section class="bento-cell bento-item">
        <header class="bento-cell__head bento-cell__head--split">
          <div class="bento-cell__title-group">
            <span
              class="bento-cell__live-dot"
              :class="systemHealthy ? '' : 'bento-cell__live-dot--alert'"
              :aria-hidden="true"
            />
            <h3 class="bento-cell__title">
              {{ t('adminDashboard.systemStatusTitle') }}
            </h3>
            <span class="bento-cell__status-text">
              {{ systemHealthy ? t('adminDashboard.systemStatusAllOk') : t('adminDashboard.systemStatusPartial') }}
            </span>
          </div>
          <el-button
            type="primary"
            link
            size="small"
            @click="router.push('/admin/settings')"
          >
            {{ t('adminDashboard.viewConfig') }}
          </el-button>
        </header>
        <div
          v-if="healthLoading"
          class="card-loading"
        >
          <el-skeleton
            :rows="4"
            animated
          />
        </div>
        <template v-else>
          <ul class="component-list">
            <li
              v-for="comp in componentStatus"
              :key="comp.key"
              class="component-item"
            >
              <div class="component-info">
                <span
                  class="component-dot"
                  :class="{ 'component-dot--healthy': comp.healthy, 'breathe-dot': comp.healthy }"
                  :aria-hidden="true"
                />
                <span class="component-name">{{ t(COMPONENT_NAME_KEYS[comp.key]) }}</span>
              </div>
              <el-tag
                :type="comp.healthy ? 'success' : 'danger'"
                size="small"
                effect="light"
              >
                {{ comp.healthy ? t('adminDashboard.statusHealthy') : t('adminDashboard.statusUnhealthy') }}
              </el-tag>
            </li>
          </ul>
        </template>
      </section>

      <section class="bento-cell bento-item">
        <header class="bento-cell__head">
          <h3 class="bento-cell__title">
            {{ t('adminDashboard.quickActions') }}
          </h3>
        </header>
        <div class="quick-actions">
          <el-button
            type="primary"
            class="magnetic-press"
            @click="router.push('/admin/templates')"
          >
            {{ t('adminDashboard.btnTemplates') }}
          </el-button>
          <el-button
            type="warning"
            class="magnetic-press"
            @click="router.push('/admin/settings')"
          >
            {{ t('adminDashboard.btnSettings') }}
          </el-button>
          <el-button
            type="info"
            class="magnetic-press"
            @click="router.push('/admin/operation-logs')"
          >
            {{ t('adminDashboard.btnOperationLogs') }}
          </el-button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { adminApi } from '@/api/adminApi'
import { ArrowUp, ArrowDown } from '@element-plus/icons-vue'

const { t } = useI18n()
const auth = useAuthStore()
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

const userTrend = computed(() => {
  if (stats.yesterday_users === 0) return 0
  return Math.round(((stats.total_users - stats.yesterday_users) / stats.yesterday_users) * 100)
})

const warningTrend = computed(() => {
  if (stats.yesterday_warnings === 0) return 0
  return Math.round(((stats.today_warnings - stats.yesterday_warnings) / stats.yesterday_warnings) * 100)
})

const assessmentTrend = computed(() => {
  if (stats.yesterday_assessments === 0) return 0
  return Math.round(((stats.total_assessments - stats.yesterday_assessments) / stats.yesterday_assessments) * 100)
})

const templateTrend = computed(() => {
  if (stats.yesterday_templates === 0) return 0
  return Math.round(((stats.active_templates - stats.yesterday_templates) / stats.yesterday_templates) * 100)
})

interface StatCard {
  key: string
  label: string
  value: string | number
  tone: 'primary' | 'warning' | 'danger' | 'success'
  trend: number
  trendType: 'success' | 'danger'
  sub: string
  action?: () => void
  actionText?: string
  actionType?: 'primary' | 'warning' | 'success' | 'info'
}

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

// 系统组件状态：使用稳定 key 作为后端映射标识，显示名通过 i18n 渲染
const COMPONENT_NAME_KEYS: Record<string, string> = {
  api: 'adminDashboard.componentApi',
  database: 'adminDashboard.componentDatabase',
  redis: 'adminDashboard.componentRedis',
  celery_worker: 'adminDashboard.componentQueue',
  storage: 'adminDashboard.componentStorage',
}

const executiveSummary = computed(() => ({
  title: t('adminDashboard.executiveSummaryTitle'),
  body: t('adminDashboard.executiveSummaryBody', {
    users: stats.total_users,
    warnings: stats.today_warnings,
    templates: stats.active_templates,
  }),
}))

const componentStatus = ref<{ key: string; healthy: boolean }[]>(
  Object.keys(COMPONENT_NAME_KEYS).map((key) => ({ key, healthy: true }))
)

const loadStats = async () => {
  statsLoading.value = true
  try {
    const data = await adminApi.getAdminStats()
    Object.assign(stats, data)
  } catch {
    ElMessage.warning(t('adminDashboard.loadStatsFailed'))
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
    ElMessage.warning(t('adminDashboard.loadHealthFailed'))
  } finally {
    healthLoading.value = false
  }
}

const handleLogout = async () => {
  try {
    await ElMessageBox.confirm(t('layout.logoutConfirm'), t('layout.logoutConfirmTitle'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await auth.logout()
  } catch {
    ElMessage.warning(t('adminDashboard.logoutFailed'))
  }
  await router.push('/login')
}

onMounted(() => {
  loadStats()
  checkHealth()
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
  margin-bottom: var(--spacing-2xl);
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--spacing-md);
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
  background: var(--danger-color);
  box-shadow: 0 0 8px rgba(214, 90, 90, 0.6);
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
  align-items: center;
  gap: var(--spacing-sm);
  flex-shrink: 0;
}

.executive-summary {
  margin: -0.5rem 0 1rem;
  padding: 1rem 1.25rem;
  border: 1px solid var(--border-extra-light);
  border-radius: 1rem;
  background: var(--bg-primary);
}

.executive-summary h3 {
  margin: 0 0 0.35rem;
  font-size: 0.95rem;
  color: var(--text-primary);
}

.executive-summary p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.6;
}

/* ===== Bento 统计区：主指标（1.3fr）+ 副指标网格（2fr 内 2x2） ===== */
.bento-stats {
  display: grid;
  grid-template-columns: 1.3fr 2fr;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.bento-stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-lg);
}

.bento-stat {
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

.bento-stat:hover {
  box-shadow: 0 12px 32px -12px rgba(59, 130, 196, 0.14);
  border-color: var(--border-light);
}

.bento-stat--hero {
  background:
    linear-gradient(180deg, rgba(59, 130, 196, 0.04) 0%, transparent 60%),
    var(--bg-primary);
  justify-content: space-between;
}

.stat-label {
  font-family: var(--font-family-mono);
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-bottom: 0.75rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.stat {
  font-family: var(--font-family-display);
  font-size: 2rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  margin: 0.25rem 0 0.5rem;
  line-height: 1;
  color: var(--text-primary);
}

.stat--hero {
  font-size: 3.25rem;
  color: var(--primary-color);
}

.stat--primary { color: var(--primary-color); }
.stat--warning { color: var(--warning-color); }
.stat--danger { color: var(--danger-color); }
.stat--success { color: var(--success-color); }

.stat-sub {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  display: block;
  margin-top: var(--spacing-xs);
}

.stat-loading {
  min-height: 44px;
}

.stat-trend {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin: 0.25rem 0;
}

.trend-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.stat-action {
  margin-top: auto;
  align-self: flex-start;
  padding-top: 0.5rem;
}

/* ===== 第二行 Bento：系统状态（宽）+ 快捷操作（窄） ===== */
.bento-grid--bottom {
  display: grid;
  grid-template-columns: 1.85fr 1fr;
  gap: var(--spacing-lg);
}

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
  flex-wrap: wrap;
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
  background: var(--success-color);
  box-shadow: 0 0 8px rgba(90, 158, 58, 0.6);
  flex-shrink: 0;
}

.bento-cell__live-dot--alert {
  background: var(--danger-color);
  box-shadow: 0 0 8px rgba(214, 90, 90, 0.6);
}

.bento-cell__status-text {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.card-loading {
  padding: var(--spacing-lg) 0;
}

/* 系统组件列表 */
.component-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.component-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--border-extra-light);
}

.component-item:last-child {
  border-bottom: none;
}

.component-info {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.component-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--danger-color);
  flex-shrink: 0;
}

.component-dot--healthy {
  background: var(--success-color);
  box-shadow: 0 0 8px rgba(90, 158, 58, 0.5);
}

.component-name {
  font-size: var(--font-size-base);
  color: var(--text-regular);
}

.quick-actions {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

/* ===== 响应式：移动端单列回退 ===== */
@media (max-width: 1024px) {
  .bento-stats,
  .bento-grid--bottom {
    grid-template-columns: 1fr;
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

  .bento-stat-grid {
    grid-template-columns: 1fr;
  }

  .stat {
    font-size: 1.75rem;
  }

  .stat--hero {
    font-size: 2.5rem;
  }
}
</style>

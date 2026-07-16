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

    <NextStepCard :next-action="nextAction" />

    <!-- Bento 网格：风险状态主视觉（2fr）+ 副卡（1fr），打破 3 等宽卡片行 -->
    <div class="bento-grid bento-grid--top">
      <!-- 主视觉：风险状态（占据更宽列，作为 Hero 数据卡） -->
      <RiskStatusCard
        :risk-report="riskReport"
        :risk-loading="riskLoading"
        :risk-error="riskError"
        :risk-color="riskColor"
        :severity-label="severityLabel"
        :severity-tag-type="severityTagType"
        @reload="loadRiskReport"
      />

      <!-- 副卡列：最近测评 + 干预计划垂直堆叠 -->
      <div class="bento-cell-stack">
        <LatestAssessmentCard
          :latest-assessment="latestAssessment"
          :loading="assessmentLoading"
          :error="assessmentError"
          :assessment-type-label="assessmentTypeLabelText"
          @reload="loadLatestAssessment"
        />
        <InterventionPlanCard
          :active-intervention="activeIntervention"
          :completed-tasks="completedTasks"
          :loading="interventionLoading"
          :error="interventionError"
          @reload="loadActiveIntervention"
        />
      </div>
    </div>

    <!-- 第二行：风险趋势（宽）+ 未读预警（窄） -->
    <div class="bento-grid bento-grid--bottom">
      <RiskTrendChart
        v-model:days="trendDays"
        :risk-trend="riskTrend"
        :loading="trendLoading"
        :error="trendError"
        @reload="loadRiskTrend"
      />
      <UnreadWarningsCard
        :unread-warnings="unreadWarnings"
        :loading="warningLoading"
        :error="warningError"
        @reload="loadWarnings"
      />
    </div>

    <!-- 第三行：最近活动时间线（全宽） -->
    <div class="dashboard-activity">
      <RecentActivityCard
        :activities="activities"
        :loading="activityLoading"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import NextStepCard from './components/user-dashboard/NextStepCard.vue'
import RiskStatusCard from './components/user-dashboard/RiskStatusCard.vue'
import LatestAssessmentCard from './components/user-dashboard/LatestAssessmentCard.vue'
import InterventionPlanCard from './components/user-dashboard/InterventionPlanCard.vue'
import RiskTrendChart from './components/user-dashboard/RiskTrendChart.vue'
import UnreadWarningsCard from './components/user-dashboard/UnreadWarningsCard.vue'
import RecentActivityCard from './components/user-dashboard/RecentActivityCard.vue'
import { useUserDashboardData } from './components/user-dashboard/useUserDashboardData'

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()

const {
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
} = useUserDashboardData()

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
  box-shadow: 0 0 8px rgba(46, 111, 168, 0.6);
}

.layout__header h2 {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: var(--font-size-display);
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

.dashboard-activity {
  margin-top: var(--spacing-lg);
}

.bento-cell-stack {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: var(--spacing-lg);
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
}
</style>

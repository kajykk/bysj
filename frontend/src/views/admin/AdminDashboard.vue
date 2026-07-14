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
        <p>{{ t('adminDashboard.welcome', { name: auth.user?.nickname || auth.user?.username || t('adminDashboard.welcomeFallback') }) }}</p>
      </div>
      <div class="layout__actions">
        <el-tag type="danger">
          {{ t('adminDashboard.tagAdmin') }}
        </el-tag>
        <el-button @click="handleLogout">
          {{ t('user.logout') }}
        </el-button>
      </div>
    </div>

    <!-- Bento 统计区：主指标卡（注册用户）+ 副指标 2x2 网格 -->
    <StatCardsSection
      :loading="statsLoading"
      :primary-stat="primaryStat"
      :secondary-stats="secondaryStats"
    />

    <!-- 第二行：系统状态（宽，Live Status）+ 快捷操作（窄） -->
    <div class="bento-grid bento-grid--bottom">
      <SystemStatusCard
        :loading="healthLoading"
        :system-healthy="systemHealthy"
        :component-status="componentStatus"
        @view-config="router.push('/admin/settings')"
      />

      <QuickActionsCard @navigate="router.push" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import StatCardsSection from './components/admin-dashboard/StatCardsSection.vue'
import SystemStatusCard from './components/admin-dashboard/SystemStatusCard.vue'
import QuickActionsCard from './components/admin-dashboard/QuickActionsCard.vue'
import { useAdminDashboardData } from './components/admin-dashboard/useAdminDashboardData'

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()

const {
  statsLoading, healthLoading, systemHealthy,
  primaryStat, secondaryStats, componentStatus,
} = useAdminDashboardData()

const handleLogout = async () => {
  try {
    await ElMessageBox.confirm(t('layout.logoutConfirm'), t('layout.logoutConfirmTitle'), { type: 'warning' })
  } catch {
    return
  }
  await auth.logout()
  await router.push('/login')
}
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
  align-items: center;
  gap: var(--spacing-sm);
  flex-shrink: 0;
}

/* ===== 第二行 Bento 布局容器：系统状态（宽）+ 快捷操作（窄） ===== */
.bento-grid--bottom {
  display: grid;
  grid-template-columns: 1.85fr 1fr;
  gap: var(--spacing-lg);
}

/* ===== 响应式：移动端单列回退 ===== */
@media (max-width: 1024px) {
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
}
</style>

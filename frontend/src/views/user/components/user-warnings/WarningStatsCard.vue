<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('userWarnings.stats.title') }}</span>
    </template>
    <div
      v-if="loading"
      class="skeleton-padding"
    >
      <SkeletonScreen
        :rows="2"
        variant="text"
      />
    </div>
    <div
      v-else
      class="stat-grid"
    >
      <div class="stat-tile">
        <div class="stat-value">
          {{ stats.total }}
        </div>
        <div class="stat-label">
          {{ t('userWarnings.stats.total') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--high">
        <div class="stat-value">
          {{ stats.highRisk }}
        </div>
        <div class="stat-label">
          {{ t('userWarnings.stats.highRisk') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--medium">
        <div class="stat-value">
          {{ stats.mediumRisk }}
        </div>
        <div class="stat-label">
          {{ t('userWarnings.stats.mediumRisk') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--low">
        <div class="stat-value">
          {{ stats.lowRisk }}
        </div>
        <div class="stat-label">
          {{ t('userWarnings.stats.lowRisk') }}
        </div>
      </div>
      <div class="stat-tile">
        <div class="stat-value">
          {{ stats.handled }}
        </div>
        <div class="stat-label">
          {{ t('userWarnings.stats.handled') }}
        </div>
      </div>
      <div class="stat-tile">
        <div class="stat-value">
          {{ stats.unread }}
        </div>
        <div class="stat-label">
          {{ t('userWarnings.stats.unread') }}
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'WarningStatsCard' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { userApi } from '@/api/userApi'
import SkeletonScreen from '@/components/common/SkeletonScreen.vue'
import { hasPermission } from '@/config/permissions'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()

const loading = ref(true)
const stats = reactive({
  total: 0,
  highRisk: 0,
  mediumRisk: 0,
  lowRisk: 0,
  handled: 0,
  unread: 0
})

const canReadWarning = () => hasPermission(auth.role, 'user.warning.read')

const loadStats = async () => {
  if (!canReadWarning()) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    // P1-15 / F-03：改用后端 SQL 层聚合端点。改前 page_size:200 拉全量预警到
    // 前端 filter，预警超 200 条时分子（分级/已处理/未读）只覆盖前 200 条，
    // 而分母用服务端 total，统计结果是错的。
    const data = await userApi.getUserWarningStats()
    stats.total = data.total
    stats.highRisk = data.high_risk
    stats.mediumRisk = data.medium_risk
    stats.lowRisk = data.low_risk
    stats.handled = data.handled
    stats.unread = data.unread
  } catch {
    // 统计加载失败时使用空值，不阻断主列表
  } finally {
    loading.value = false
  }
}

onMounted(loadStats)
defineExpose({ loadStats })
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.skeleton-padding {
  padding: var(--spacing-md) 0;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--spacing-md);
}

.stat-tile {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  background-color: var(--bg-page);
  border-left: 3px solid var(--border-light);
}

.stat-tile--high {
  border-left-color: var(--danger-color);
}

.stat-tile--medium {
  border-left-color: var(--warning-color);
}

.stat-tile--low {
  border-left-color: var(--success-color);
}

.stat-value {
  font-size: var(--font-size-stat);
  font-weight: var(--font-weight-bold);
  line-height: 1.1;
  color: var(--text-primary);
}

.stat-tile--high .stat-value {
  color: var(--danger-color);
}

.stat-tile--medium .stat-value {
  color: var(--warning-color);
}

.stat-tile--low .stat-value {
  color: var(--success-color);
}

.stat-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>

<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('adminAlerts.stats.title') }}</span>
    </template>
    <div
      v-if="loading"
      class="skeleton-padding"
    >
      <el-skeleton
        :rows="2"
        animated
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
          {{ t('adminAlerts.stats.total') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--p0">
        <div class="stat-value">
          {{ stats.p0 }}
        </div>
        <div class="stat-label">
          {{ t('adminAlerts.severityLabelP0') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--p1">
        <div class="stat-value">
          {{ stats.p1 }}
        </div>
        <div class="stat-label">
          {{ t('adminAlerts.severityLabelP1') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--p2">
        <div class="stat-value">
          {{ stats.p2 }}
        </div>
        <div class="stat-label">
          {{ t('adminAlerts.severityLabelP2') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--firing">
        <div class="stat-value">
          {{ stats.firing }}
        </div>
        <div class="stat-label">
          {{ t('adminAlerts.statusFiring') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--resolved">
        <div class="stat-value">
          {{ stats.resolved }}
        </div>
        <div class="stat-label">
          {{ t('adminAlerts.statusResolved') }}
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'AlertStatsCard' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { alertsApi } from '@/api/alertsApi'

const { t } = useI18n()

const loading = ref(true)
const stats = reactive({
  total: 0,
  p0: 0,
  p1: 0,
  p2: 0,
  firing: 0,
  resolved: 0
})

const loadStats = async () => {
  loading.value = true
  try {
    // 聚合告警历史（默认 history 视图），呈现全局严重度/状态分布
    const data = await alertsApi.listAlertHistory({ page: 1, page_size: 200 })
    const items = data.items || []
    stats.total = data.total ?? items.length
    stats.p0 = items.filter((i) => i.severity === 'P0').length
    stats.p1 = items.filter((i) => i.severity === 'P1').length
    stats.p2 = items.filter((i) => i.severity === 'P2').length
    stats.firing = items.filter((i) => i.status === 'firing').length
    stats.resolved = items.filter((i) => i.status === 'resolved').length
  } catch {
    // 统计加载失败时使用空值，不阻断主列表
  } finally {
    loading.value = false
  }
}

onMounted(loadStats)
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

.stat-tile--p0 {
  border-left-color: var(--danger-color);
}

.stat-tile--p1 {
  border-left-color: var(--warning-color);
}

.stat-tile--p2 {
  border-left-color: var(--info-color);
}

.stat-tile--firing {
  border-left-color: var(--danger-color);
}

.stat-tile--resolved {
  border-left-color: var(--success-color);
}

.stat-value {
  font-size: var(--font-size-stat);
  font-weight: var(--font-weight-bold);
  line-height: 1.1;
  color: var(--text-primary);
}

.stat-tile--p0 .stat-value {
  color: var(--danger-color);
}

.stat-tile--p1 .stat-value {
  color: var(--warning-color);
}

.stat-tile--p2 .stat-value {
  color: var(--info-color);
}

.stat-tile--firing .stat-value {
  color: var(--danger-color);
}

.stat-tile--resolved .stat-value {
  color: var(--success-color);
}

.stat-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>

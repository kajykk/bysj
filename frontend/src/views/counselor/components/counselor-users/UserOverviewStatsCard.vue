<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('counselorUsers.stats.title') }}</span>
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
          {{ t('counselorUsers.stats.total') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--none">
        <div class="stat-value">
          {{ stats.none }}
        </div>
        <div class="stat-label">
          {{ t('counselorUsers.stats.none') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--low">
        <div class="stat-value">
          {{ stats.low }}
        </div>
        <div class="stat-label">
          {{ t('counselorUsers.stats.low') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--medium">
        <div class="stat-value">
          {{ stats.medium }}
        </div>
        <div class="stat-label">
          {{ t('counselorUsers.stats.medium') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--high">
        <div class="stat-value">
          {{ stats.high }}
        </div>
        <div class="stat-label">
          {{ t('counselorUsers.stats.high') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--critical">
        <div class="stat-value">
          {{ stats.critical }}
        </div>
        <div class="stat-label">
          {{ t('counselorUsers.stats.critical') }}
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'UserOverviewStatsCard' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { counselorApi, type UserManageItem } from '@/api/counselorApi'

const { t } = useI18n()

const normalizeRiskLevel = (
  value: UserManageItem['risk_level'] | UserManageItem['latest_risk_level']
): number => {
  if (typeof value === 'number') return value
  const map: Record<string, number> = { none: 0, low: 1, medium: 2, high: 3, critical: 4 }
  return map[String(value ?? 'none')] ?? 0
}

const loading = ref(true)
const stats = reactive({
  total: 0,
  none: 0,
  low: 0,
  medium: 0,
  high: 0,
  critical: 0
})

const loadStats = async () => {
  loading.value = true
  try {
    const data = await counselorApi.getCounselorUsers({ page: 1, page_size: 200 })
    const items = data.items || []
    stats.total = data.total ?? items.length
    stats.none = items.filter(
      (i) => normalizeRiskLevel(i.risk_level ?? i.latest_risk_level) === 0
    ).length
    stats.low = items.filter(
      (i) => normalizeRiskLevel(i.risk_level ?? i.latest_risk_level) === 1
    ).length
    stats.medium = items.filter(
      (i) => normalizeRiskLevel(i.risk_level ?? i.latest_risk_level) === 2
    ).length
    stats.high = items.filter(
      (i) => normalizeRiskLevel(i.risk_level ?? i.latest_risk_level) === 3
    ).length
    stats.critical = items.filter(
      (i) => normalizeRiskLevel(i.risk_level ?? i.latest_risk_level) === 4
    ).length
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

.stat-tile--none {
  border-left-color: var(--info-color);
}

.stat-tile--low {
  border-left-color: var(--success-color);
}

.stat-tile--medium {
  border-left-color: var(--warning-color);
}

.stat-tile--high {
  border-left-color: var(--danger-color);
}

.stat-tile--critical {
  border-left-color: #b5384a;
}

.stat-value {
  font-size: var(--font-size-stat);
  font-weight: var(--font-weight-bold);
  line-height: 1.1;
  color: var(--text-primary);
}

.stat-tile--none .stat-value {
  color: var(--info-color);
}

.stat-tile--low .stat-value {
  color: var(--success-color);
}

.stat-tile--medium .stat-value {
  color: var(--warning-color);
}

.stat-tile--high .stat-value {
  color: var(--danger-color);
}

.stat-tile--critical .stat-value {
  color: #b5384a;
}

.stat-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>

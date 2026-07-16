<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('canary.stats.title') }}</span>
    </template>
    <div class="stat-grid">
      <div class="stat-tile">
        <div class="stat-value">
          {{ stats.total }}
        </div>
        <div class="stat-label">
          {{ t('canary.stats.total') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--running">
        <div class="stat-value">
          {{ stats.running }}
        </div>
        <div class="stat-label">
          {{ t('canary.running') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--paused">
        <div class="stat-value">
          {{ stats.paused }}
        </div>
        <div class="stat-label">
          {{ t('canary.paused') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--completed">
        <div class="stat-value">
          {{ stats.completed }}
        </div>
        <div class="stat-label">
          {{ t('canary.stats.completed') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--rolled-back">
        <div class="stat-value">
          {{ stats.rolledBack }}
        </div>
        <div class="stat-label">
          {{ t('canary.stats.rolledBack') }}
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'CanaryStatsCard' })
import { useI18n } from 'vue-i18n'

interface CanaryStats {
  total: number
  running: number
  paused: number
  completed: number
  rolledBack: number
}

withDefaults(
  defineProps<{
    stats: CanaryStats
  }>(),
  {
    stats: () => ({
      total: 0,
      running: 0,
      paused: 0,
      completed: 0,
      rolledBack: 0
    })
  }
)

const { t } = useI18n()
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
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

.stat-tile--running {
  border-left-color: var(--success-color);
}

.stat-tile--paused {
  border-left-color: var(--warning-color);
}

.stat-tile--completed {
  border-left-color: var(--info-color);
}

.stat-tile--rolled-back {
  border-left-color: var(--danger-color);
}

.stat-value {
  font-size: var(--font-size-stat);
  font-weight: var(--font-weight-bold);
  line-height: 1.1;
  color: var(--text-primary);
}

.stat-tile--running .stat-value {
  color: var(--success-color);
}

.stat-tile--paused .stat-value {
  color: var(--warning-color);
}

.stat-tile--completed .stat-value {
  color: var(--info-color);
}

.stat-tile--rolled-back .stat-value {
  color: var(--danger-color);
}

.stat-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>

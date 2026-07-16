<template>
  <el-card class="stats-card">
    <template #header>
      <span class="card-title">{{ t('counselorReviews.statsTitle') }}</span>
    </template>
    <div class="stat-grid">
      <div class="stat-tile">
        <div class="stat-value">
          {{ stats.total }}
        </div>
        <div class="stat-label">
          {{ t('counselorReviews.statTotal') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--pending">
        <div class="stat-value">
          {{ stats.pending }}
        </div>
        <div class="stat-label">
          {{ t('counselorReviews.statPending') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--in-review">
        <div class="stat-value">
          {{ stats.in_review }}
        </div>
        <div class="stat-label">
          {{ t('counselorReviews.statInReview') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--resolved">
        <div class="stat-value">
          {{ stats.resolved }}
        </div>
        <div class="stat-label">
          {{ t('counselorReviews.statResolved') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--escalated">
        <div class="stat-value">
          {{ stats.escalated }}
        </div>
        <div class="stat-label">
          {{ t('counselorReviews.statEscalated') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--crisis">
        <div class="stat-value">
          {{ stats.crisis_count }}
        </div>
        <div class="stat-label">
          {{ t('counselorReviews.statCrisis') }}
        </div>
      </div>
      <div class="stat-tile stat-tile--high-risk">
        <div class="stat-value">
          {{ stats.high_risk_count }}
        </div>
        <div class="stat-label">
          {{ t('counselorReviews.statHighRisk') }}
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'ReviewStatsCard' })
import { useI18n } from 'vue-i18n'
import type { ReviewStats } from '@/api/counselorApi'

withDefaults(
  defineProps<{
    stats: ReviewStats
  }>(),
  {
    stats: () => ({
      total: 0,
      pending: 0,
      in_review: 0,
      resolved: 0,
      escalated: 0,
      crisis_count: 0,
      high_risk_count: 0
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

.stat-tile--pending {
  border-left-color: var(--warning-color);
}

.stat-tile--in-review {
  border-left-color: var(--primary-color);
}

.stat-tile--resolved {
  border-left-color: var(--success-color);
}

.stat-tile--escalated {
  border-left-color: var(--danger-color);
}

.stat-tile--crisis {
  border-left-color: #b5384a;
}

.stat-tile--high-risk {
  border-left-color: var(--danger-color);
}

.stat-value {
  font-size: var(--font-size-stat);
  font-weight: var(--font-weight-bold);
  line-height: 1.1;
  color: var(--text-primary);
}

.stat-tile--pending .stat-value {
  color: var(--warning-color);
}

.stat-tile--in-review .stat-value {
  color: var(--primary-color);
}

.stat-tile--resolved .stat-value {
  color: var(--success-color);
}

.stat-tile--escalated .stat-value {
  color: var(--danger-color);
}

.stat-tile--crisis .stat-value {
  color: #b5384a;
}

.stat-tile--high-risk .stat-value {
  color: var(--danger-color);
}

.stat-label {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>

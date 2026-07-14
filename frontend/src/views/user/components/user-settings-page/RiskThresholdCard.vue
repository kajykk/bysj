<template>
  <el-card>
    <template #header>
      <span class="card-title">{{ t('userSettings.riskThreshold.title') }}</span>
    </template>
    <p class="card-desc">
      {{ t('userSettings.riskThreshold.desc') }}
    </p>
    <ul class="threshold-list">
      <li class="threshold-item threshold-item--high">
        <span class="dot" />
        <span class="threshold-label">{{ t('userSettings.riskThreshold.high') }}</span>
        <span class="threshold-range">{{ t('userSettings.riskThreshold.highRange') }}</span>
      </li>
      <li class="threshold-item threshold-item--moderate">
        <span class="dot" />
        <span class="threshold-label">{{ t('userSettings.riskThreshold.moderate') }}</span>
        <span class="threshold-range">{{ t('userSettings.riskThreshold.moderateRange') }}</span>
      </li>
      <li class="threshold-item threshold-item--low">
        <span class="dot" />
        <span class="threshold-label">{{ t('userSettings.riskThreshold.low') }}</span>
        <span class="threshold-range">{{ t('userSettings.riskThreshold.lowRange') }}</span>
      </li>
    </ul>
    <p class="card-note">
      {{ t('userSettings.riskThreshold.note') }}
    </p>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'RiskThresholdCard' })
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.card-desc {
  margin: 0 0 var(--spacing-md);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: 1.6;
}

.threshold-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.threshold-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  background-color: var(--bg-page);
  border-left: 3px solid transparent;
}

.threshold-item--high {
  border-left-color: var(--danger-color);
}

.threshold-item--moderate {
  border-left-color: var(--warning-color);
}

.threshold-item--low {
  border-left-color: var(--success-color);
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: var(--radius-circle);
  flex-shrink: 0;
}

.threshold-item--high .dot {
  background-color: var(--danger-color);
}

.threshold-item--moderate .dot {
  background-color: var(--warning-color);
}

.threshold-item--low .dot {
  background-color: var(--success-color);
}

.threshold-label {
  font-weight: var(--font-weight-medium);
}

.threshold-range {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.card-note {
  margin: var(--spacing-md) 0 0;
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-light);
  font-size: var(--font-size-extra-small);
  color: var(--text-placeholder);
  line-height: 1.5;
}
</style>

<template>
  <el-card>
    <template #header>
      <div class="plan-header">
        <span class="card-title">{{ plan.plan_name }}</span>
        <div class="plan-meta">
          <el-tag
            :type="riskLevelTag(plan.risk_level)"
            size="small"
          >
            {{ t('userIntervention.riskLevelLabel') }} {{ plan.risk_level }}
          </el-tag>
          <span
            v-if="plan.start_date"
            class="plan-date"
          >{{ t('userIntervention.startDatePrefix') }}{{ plan.start_date }}</span>
        </div>
      </div>
    </template>
    <div class="progress-wrap">
      <span class="progress-label">{{ t('userIntervention.progressLabel') }}</span>
      <el-progress
        :percentage="plan.progress"
        :stroke-width="16"
        :text-inside="true"
      />
    </div>
    <div
      v-if="plan.dominant_modality"
      class="plan-modality"
    >
      {{ t('userIntervention.dominantModalityPrefix') }}{{ getModalityLabel(plan.dominant_modality) }}
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ActiveIntervention } from '@/api/userTypes'
import { MODALITY_LABEL_KEYS, riskLevelTag } from './sharedInterventionUtils'

defineProps<{
  plan: ActiveIntervention['plan']
}>()

const { t } = useI18n()

const getModalityLabel = (modality: string | null | undefined) => {
  if (!modality) return ''
  const key = MODALITY_LABEL_KEYS[modality]
  return key ? t(`userIntervention.${key}`) : modality
}
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.plan-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md);
}

.plan-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.plan-date {
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}

.progress-wrap {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.progress-label {
  font-size: var(--font-size-small);
  color: var(--text-regular);
  white-space: nowrap;
}

.progress-wrap .el-progress {
  flex: 1;
}

.plan-modality {
  margin-top: var(--spacing-md);
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}
</style>

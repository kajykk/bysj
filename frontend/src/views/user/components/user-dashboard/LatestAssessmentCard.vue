<template>
  <section class="bento-cell bento-item shimmer-sweep">
    <header class="bento-cell__head">
      <h3 class="bento-cell__title">
        {{ t('userDashboard.latestAssessmentTitle') }}
      </h3>
    </header>
    <div
      v-if="loading"
      class="card-loading"
    >
      <SkeletonScreen
        :rows="2"
        variant="text"
      />
    </div>
    <EmptyState
      v-else-if="error"
      :title="t('userDashboard.loadFailed')"
      :description="error"
      :image-size="40"
    >
      <template #action>
        <el-button
          type="primary"
          plain
          @click="emit('reload')"
        >
          {{ t('userDashboard.btnReload') }}
        </el-button>
      </template>
    </EmptyState>
    <template v-else-if="latestAssessment">
      <div class="stat-row">
        <span class="stat-label">{{ t('userDashboard.assessmentTypeLabel') }}</span>
        <el-tag size="small">
          {{ assessmentTypeLabel }}
        </el-tag>
      </div>
      <div class="stat-row">
        <span class="stat-label">{{ t('userDashboard.assessmentTimeLabel') }}</span>
        <span class="stat-value tabular-nums">{{ formatDate(latestAssessment.created_at, 'MM/DD HH:mm') }}</span>
      </div>
      <el-button
        type="primary"
        plain
        class="cell-action"
        @click="router.push('/user/risk')"
      >
        {{ t('userDashboard.btnStartAssessment') }}
      </el-button>
    </template>
    <template v-else>
      <EmptyState
        variant="assessment"
        :title="t('userDashboard.emptyNoRecord')"
        :description="t('userDashboard.emptyNoRecordDesc')"
        :image-size="40"
      >
        <template #action>
          <el-button
            type="primary"
            plain
            @click="router.push('/user/risk')"
          >
            {{ t('userDashboard.btnStartAssessment') }}
          </el-button>
        </template>
      </EmptyState>
    </template>
  </section>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import EmptyState from '@/components/common/EmptyState.vue'
import SkeletonScreen from '@/components/common/SkeletonScreen.vue'
import { formatDate } from '@/utils/formatUtils'
import type { DataHistoryItem } from '@/api/userTypes'

defineProps<{
  latestAssessment: DataHistoryItem | null
  loading: boolean
  error: string
  assessmentTypeLabel: string
}>()

const emit = defineEmits<{ reload: [] }>()

const { t } = useI18n()
const router = useRouter()
</script>

<style scoped lang="scss">
@use '../../../../styles/card-mixins' as *;

@include bento-cell;

.card-loading {
  padding: var(--spacing-lg) 0;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.stat-label {
  font-size: var(--font-size-small);
  color: var(--text-regular);
}

.stat-value {
  font-size: var(--font-size-small);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.cell-action {
  margin-top: auto;
  align-self: flex-start;
  padding-top: 0.75rem;
}
</style>

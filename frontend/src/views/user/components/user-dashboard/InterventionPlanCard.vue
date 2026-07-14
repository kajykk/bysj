<template>
  <section class="bento-cell bento-item shimmer-sweep">
    <header class="bento-cell__head">
      <h3 class="bento-cell__title">
        {{ t('userDashboard.interventionPlanTitle') }}
      </h3>
    </header>
    <div
      v-if="loading"
      class="card-loading"
    >
      <el-skeleton
        :rows="2"
        animated
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
    <template v-else-if="activeIntervention.plan.id">
      <div class="stat-row">
        <span class="stat-label">{{ t('userDashboard.planNameLabel') }}</span>
        <span class="stat-value">{{ activeIntervention.plan.plan_name }}</span>
      </div>
      <el-progress
        :percentage="activeIntervention.plan.progress"
        :stroke-width="10"
        class="intervention-progress"
      />
      <div class="stat-row">
        <span class="stat-label">{{ t('userDashboard.todayTasksLabel') }}</span>
        <span class="stat-value tabular-nums">{{ completedTasks }}/{{ activeIntervention.tasks.length }}</span>
      </div>
      <el-button
        type="primary"
        plain
        class="cell-action"
        @click="router.push('/user/intervention')"
      >
        {{ t('userDashboard.btnViewDetail') }}
      </el-button>
    </template>
    <template v-else>
      <EmptyState
        :title="t('userDashboard.emptyNoActivePlan')"
        :description="t('userDashboard.emptyNoActivePlanDesc')"
        :image-size="40"
      >
        <template #action>
          <el-button
            type="primary"
            plain
            @click="router.push('/user/risk')"
          >
            {{ t('userDashboard.btnAssessFirst') }}
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
import type { ActiveIntervention } from '@/api/userRiskApi'

defineProps<{
  activeIntervention: ActiveIntervention
  completedTasks: number
  loading: boolean
  error: string
}>()

const emit = defineEmits<{ reload: [] }>()

const { t } = useI18n()
const router = useRouter()
</script>

<style scoped>
.bento-cell {
  background: var(--bg-primary);
  border: 1px solid var(--border-extra-light);
  border-radius: 1.25rem;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  box-shadow: 0 1px 2px rgba(15, 22, 32, 0.04);
  transition: box-shadow 0.3s var(--transition-ease-out),
    border-color 0.3s var(--transition-ease-out);
}

.bento-cell:hover {
  box-shadow: 0 12px 32px -12px rgba(46, 111, 168, 0.14);
  border-color: var(--border-light);
}

.bento-cell__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1.125rem;
}

.bento-cell__title {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: 0.9375rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

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

.intervention-progress {
  margin: var(--spacing-sm) 0;
}

.cell-action {
  margin-top: auto;
  align-self: flex-start;
  padding-top: 0.75rem;
}
</style>

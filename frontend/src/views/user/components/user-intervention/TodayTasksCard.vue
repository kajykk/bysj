<template>
  <el-card class="section-card">
    <template #header>
      <span class="card-title">{{ t('userIntervention.todayTasksTitle') }}</span>
    </template>
    <div
      v-if="tasks.length === 0"
      class="text-muted"
    >
      {{ t('userIntervention.emptyTodayTasks') }}
    </div>
    <div
      v-for="task in tasks"
      :key="task.id"
      class="task-item"
    >
      <div class="task-left">
        <el-tag
          :type="taskStatusTag(task.today_status)"
          size="small"
          effect="dark"
        >
          {{ taskStatusLabel(task.today_status) }}
        </el-tag>
        <div class="task-info">
          <span class="task-name">{{ task.task_name }}</span>
          <span class="task-desc">{{ task.description }}</span>
        </div>
      </div>
      <div class="task-right">
        <span class="task-meta">{{ getScheduleLabel(task.schedule) }} · {{ task.duration_minutes }}{{ t('userIntervention.durationUnit') }}</span>
        <div class="task-actions">
          <el-button
            v-if="task.today_status === 'pending' || task.today_status === 'postponed'"
            type="success"
            size="small"
            :loading="taskPendingIds.has(task.id) && taskActionType[task.id] === 'complete'"
            @click="emit('complete', task)"
          >
            {{ t('userIntervention.btnComplete') }}
          </el-button>
          <el-button
            v-if="task.today_status === 'pending' || task.today_status === 'postponed'"
            size="small"
            :loading="taskPendingIds.has(task.id) && taskActionType[task.id] === 'skip'"
            @click="emit('skip', task)"
          >
            {{ t('userIntervention.btnSkip') }}
          </el-button>
          <el-button
            v-if="task.today_status === 'pending' || task.today_status === 'postponed'"
            size="small"
            :loading="taskPendingIds.has(task.id) && taskActionType[task.id] === 'postpone'"
            @click="emit('postpone', task)"
          >
            {{ t('userIntervention.btnPostpone') }}
          </el-button>
          <el-button
            v-if="task.today_status === 'completed'"
            type="primary"
            size="small"
            :loading="taskPendingIds.has(task.id) && taskActionType[task.id] === 'feedback'"
            @click="emit('feedback', task)"
          >
            {{ t('userIntervention.btnFeedback') }}
          </el-button>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ActiveIntervention } from '@/api/userTypes'
import type { InterventionTaskItem } from '@/api/userInterventionApi'
import { SCHEDULE_LABEL_KEYS, TASK_STATUS_LABEL_KEYS, taskStatusTag } from './sharedInterventionUtils'

defineProps<{
  tasks: ActiveIntervention['tasks']
  taskPendingIds: Set<number>
  taskActionType: Record<number, string>
}>()

const emit = defineEmits<{
  (e: 'complete', task: InterventionTaskItem): void
  (e: 'skip', task: InterventionTaskItem): void
  (e: 'postpone', task: InterventionTaskItem): void
  (e: 'feedback', task: InterventionTaskItem): void
}>()

const { t } = useI18n()

const getScheduleLabel = (schedule: string) => {
  const key = SCHEDULE_LABEL_KEYS[schedule]
  return key ? t(`userIntervention.${key}`) : schedule
}

const taskStatusLabel = (status: string) => {
  const key = TASK_STATUS_LABEL_KEYS[status]
  return key ? t(`userIntervention.${key}`) : status
}
</script>

<style scoped>
.section-card {
  margin-top: var(--spacing-lg);
}

.card-title {
  font-weight: var(--font-weight-semibold);
}

.task-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: var(--spacing-md) 0;
  border-bottom: 1px solid var(--border-lighter);
}

.task-item:last-child {
  border-bottom: none;
}

.task-left {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
  flex: 1;
}

.task-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.task-name {
  font-weight: var(--font-weight-medium);
  font-size: var(--font-size-base);
}

.task-desc {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.task-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--spacing-xs);
}

.task-meta {
  font-size: var(--font-size-extra-small);
  color: var(--text-disabled);
}

.task-actions {
  display: flex;
  gap: var(--spacing-xs);
}

.text-muted {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}
</style>

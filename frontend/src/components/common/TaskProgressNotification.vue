<template>
  <Transition name="task-progress-slide">
    <div
      v-if="allTasks.length > 0"
      class="task-progress-notification"
      role="region"
      aria-live="polite"
      :aria-label="t('taskProgress.defaultTitle')"
    >
      <div class="task-progress-header">
        <span class="task-progress-title">{{ t('taskProgress.defaultTitle') }}</span>
        <el-button
          v-if="!hasActiveTasks"
          text
          size="small"
          :aria-label="t('common.close')"
          @click="clearAll"
        >
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
      <div class="task-progress-list">
        <div
          v-for="task in allTasks"
          :key="task.job_id"
          class="task-progress-item"
          :class="`task-progress-item--${task.status}`"
        >
          <div class="task-progress-item-header">
            <span class="task-progress-item-title">{{ getTaskTitle(task.job_type) }}</span>
            <span
              class="task-progress-item-status"
              :class="`status--${task.status}`"
            >
              {{ getStatusText(task.status) }}
            </span>
          </div>
          <el-progress
            :percentage="task.progress"
            :status="getProgressStatus(task.status)"
            :stroke-width="6"
            :show-text="true"
            :duration="0.3"
          />
          <div
            v-if="task.status === 'failed' && task.error"
            class="task-progress-item-error"
            :title="task.error"
          >
            {{ task.error }}
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { useTaskProgress } from '@/composables/useTaskProgress'

const { t } = useI18n()
const { activeTasks, completedTasks, failedTasks, hasActiveTasks, clearAll } =
  useTaskProgress()

// 合并显示所有任务, 活跃的在前, 已完成的在后
const allTasks = computed(() => {
  return [...activeTasks.value, ...completedTasks.value, ...failedTasks.value].slice(0, 5)
})

function getTaskTitle(jobType: string): string {
  switch (jobType) {
    case 'pdf':
      return t('taskProgress.pdfTitle')
    case 'excel':
      return t('taskProgress.excelTitle')
    case 'training':
      return t('taskProgress.trainingTitle')
    default:
      return t('taskProgress.defaultTitle')
  }
}

function getStatusText(status: string): string {
  switch (status) {
    case 'queued':
      return t('taskProgress.queued')
    case 'running':
      return t('taskProgress.running')
    case 'completed':
      return t('taskProgress.completed')
    case 'failed':
      return t('taskProgress.failed')
    default:
      return ''
  }
}

function getProgressStatus(
  status: string,
): 'success' | 'exception' | 'warning' | undefined {
  switch (status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'exception'
    default:
      return undefined
  }
}
</script>

<style scoped lang="scss">
.task-progress-notification {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2000;
  width: 340px;
  max-width: calc(100vw - 48px);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-modal);
  border: 1px solid var(--border-lighter);
  overflow: hidden;
}

.task-progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-extra-light);
  background: var(--bg-page);
}

.task-progress-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.task-progress-list {
  max-height: 400px;
  overflow-y: auto;
  padding: 8px;
}

.task-progress-item {
  padding: 12px;
  border-radius: var(--radius-sm);
  transition: background-color 0.2s ease;

  & + .task-progress-item {
    margin-top: 4px;
  }

  &:hover {
    background: var(--bg-hover);
  }

  &--completed {
    background: var(--success-light);
  }

  &--failed {
    background: var(--danger-light);
  }
}

.task-progress-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.task-progress-item-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.task-progress-item-status {
  font-size: 12px;
  font-weight: 500;

  &.status--queued {
    color: var(--info-color);
  }

  &.status--running {
    color: var(--primary-color);
  }

  &.status--completed {
    color: var(--success-color);
  }

  &.status--failed {
    color: var(--danger-color);
  }
}

.task-progress-item-error {
  margin-top: 8px;
  font-size: 12px;
  color: var(--danger-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

// 进度条样式覆盖, 匹配设计令牌
:deep(.el-progress-bar__outer) {
  background-color: var(--border-extra-light);
}

:deep(.el-progress-bar__inner) {
  transition: width 0.3s ease;
}

:deep(.el-progress__text) {
  font-size: 12px !important;
  color: var(--text-secondary);
}

// Transition 动画
.task-progress-slide-enter-active,
.task-progress-slide-leave-active {
  transition:
    transform 0.3s ease,
    opacity 0.3s ease;
}

.task-progress-slide-enter-from,
.task-progress-slide-leave-to {
  transform: translateX(20px);
  opacity: 0;
}

// 响应式: 移动端调整
@media (max-width: 768px) {
  .task-progress-notification {
    right: 12px;
    bottom: 12px;
    left: 12px;
    width: auto;
    max-width: none;
  }
}
</style>

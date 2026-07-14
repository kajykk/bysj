<template>
  <el-dialog
    :model-value="visible"
    :title="t('adminTemplates.previewTitle')"
    width="600px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <div
      v-if="row"
      class="preview-content"
    >
      <el-descriptions
        :column="1"
        border
      >
        <el-descriptions-item :label="t('adminTemplates.previewTemplateName')">
          {{ row.template_name }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminTemplates.previewApplicableLevels')">
          <el-tag
            v-for="lv in row.applicable_levels"
            :key="lv"
            size="small"
            class="level-tag"
          >
            {{ t('adminTemplates.levelTag', { level: lv }) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminTemplates.previewEstimatedWeeks')">
          {{ row.estimated_weeks != null ? t('adminTemplates.previewEstimatedWeeksValue', { count: row.estimated_weeks }) : '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminTemplates.previewStatus')">
          <el-tag
            :type="row.status === 'active' ? 'success' : 'info'"
            size="small"
          >
            {{ row.status === 'active' ? t('adminTemplates.statusActive') : t('adminTemplates.statusInactive') }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminTemplates.previewTaskList')">
          <div
            v-if="row.task_list?.length"
            class="task-list"
          >
            <div
              v-for="(task, idx) in row.task_list"
              :key="task.task_name + '-' + idx"
              class="task-item"
            >
              <span class="task-index">{{ Number(idx) + 1 }}</span>
              <span class="task-name">{{ task.task_name }}</span>
              <el-tag
                size="small"
                type="info"
              >
                {{ task.task_type }}
              </el-tag>
              <span class="task-schedule">{{ task.schedule }}</span>
              <span
                v-if="task.duration_minutes"
                class="task-duration"
              >{{ t('adminTemplates.taskDuration', { minutes: task.duration_minutes }) }}</span>
            </div>
          </div>
          <span
            v-else
            class="text-muted"
          >{{ t('adminTemplates.noTasks') }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </div>
    <template #footer>
      <el-button @click="emit('update:visible', false)">
        {{ t('common.close') }}
      </el-button>
      <el-button
        type="primary"
        @click="emit('edit'); emit('update:visible', false)"
      >
        {{ t('adminTemplates.btnEdit') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { TemplateItem } from '@/api/adminApi'

defineProps<{
  visible: boolean
  row: TemplateItem | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'edit'): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.level-tag {
  margin-right: var(--spacing-xs);
}

.preview-content {
  padding: var(--spacing-sm) 0;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.task-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-page);
  border-radius: var(--radius-base);
}

.task-index {
  width: 20px;
  height: 20px;
  border-radius: var(--radius-circle);
  background: var(--primary-color);
  color: var(--text-inverse);
  font-size: var(--font-size-micro);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.task-name {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  flex: 1;
}

.task-schedule {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.task-duration {
  font-size: var(--font-size-extra-small);
  color: var(--text-regular);
}

.text-muted {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}
</style>

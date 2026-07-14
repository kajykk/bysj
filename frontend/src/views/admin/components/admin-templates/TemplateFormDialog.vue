<template>
  <el-dialog
    :model-value="visible"
    :title="isEditMode ? t('adminTemplates.formTitleEdit') : t('adminTemplates.formTitleCreate')"
    width="600px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form
      :model="form"
      label-width="100px"
    >
      <el-form-item
        :label="t('adminTemplates.formTemplateName')"
        required
      >
        <el-input
          v-model="form.template_name"
          :placeholder="t('adminTemplates.formTemplateNamePlaceholder')"
        />
      </el-form-item>
      <el-form-item
        :label="t('adminTemplates.formApplicableLevels')"
        required
      >
        <el-select
          v-model="form.applicable_levels"
          multiple
          style="width: 100%"
        >
          <el-option
            :label="t('adminTemplates.levelOption1')"
            :value="1"
          />
          <el-option
            :label="t('adminTemplates.levelOption2')"
            :value="2"
          />
          <el-option
            :label="t('adminTemplates.levelOption3')"
            :value="3"
          />
          <el-option
            :label="t('adminTemplates.levelOption4')"
            :value="4"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('adminTemplates.formEstimatedWeeks')">
        <el-input-number
          v-model="form.estimated_weeks"
          :min="1"
          :max="52"
        />
      </el-form-item>
      <el-form-item :label="t('adminTemplates.formStatus')">
        <el-select
          v-model="form.status"
          style="width: 200px"
        >
          <el-option
            :label="t('adminTemplates.statusOptionActive')"
            value="active"
          />
          <el-option
            :label="t('adminTemplates.statusOptionInactive')"
            value="inactive"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('adminTemplates.formTaskList')">
        <el-input
          v-model="taskListJson"
          type="textarea"
          :rows="6"
          :placeholder="taskListPlaceholder"
        />
        <div class="hint">
          {{ t('adminTemplates.formTaskListHint', { types: TASK_TYPES.join('、') }) }}
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:visible', false)">
        {{ t('common.cancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="loading"
        @click="handleSubmit"
      >
        {{ t('common.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { TASK_TYPES, TASK_TYPE_SET } from '@/api/taskTypes'
import type { TemplateItem } from '@/api/adminApi'
import {
  DEFAULT_TEMPLATE_FORM,
  buildTaskListPlaceholder,
  serializeTaskList,
  type TaskItem,
  type TemplateFormState,
  type TemplateUpsertPayload,
} from './sharedTemplatesUtils'

const props = defineProps<{
  visible: boolean
  isEditMode: boolean
  loading: boolean
  editingRow: TemplateItem | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'submit', payload: TemplateUpsertPayload): void
}>()

const { t } = useI18n()

const form = reactive<TemplateFormState>({ ...DEFAULT_TEMPLATE_FORM })
const taskListJson = ref('[]')

const taskListPlaceholder = computed(() => buildTaskListPlaceholder(t))

// 对话框打开时根据模式初始化表单（匹配原 openCreate/openEdit 行为）
watch(
  () => props.visible,
  (val) => {
    if (!val) return
    if (props.isEditMode && props.editingRow) {
      const row = props.editingRow
      form.template_name = row.template_name
      form.applicable_levels = [...row.applicable_levels]
      form.estimated_weeks = row.estimated_weeks ?? 4
      form.status = (row.status as 'active' | 'inactive')
      taskListJson.value = serializeTaskList(row.task_list)
    } else {
      form.template_name = DEFAULT_TEMPLATE_FORM.template_name
      form.applicable_levels = [...DEFAULT_TEMPLATE_FORM.applicable_levels]
      form.estimated_weeks = DEFAULT_TEMPLATE_FORM.estimated_weeks
      form.status = DEFAULT_TEMPLATE_FORM.status
      taskListJson.value = '[]'
    }
  }
)

const handleSubmit = async () => {
  if (!form.template_name.trim()) {
    ElMessage.warning(t('adminTemplates.errorTemplateNameRequired'))
    return
  }
  if (!form.applicable_levels.length) {
    ElMessage.warning(t('adminTemplates.errorLevelsRequired'))
    return
  }
  let taskList: TaskItem[] = []
  try {
    const parsed = JSON.parse(taskListJson.value)
    if (!Array.isArray(parsed)) throw new Error('任务列表必须是数组')
    taskList = parsed as unknown as TaskItem[]
  } catch {
    ElMessage.warning(t('adminTemplates.errorTaskListJsonInvalid'))
    return
  }
  const invalidTask = taskList.find((task) => typeof task.task_name !== 'string' || !TASK_TYPE_SET.has(task.task_type))
  if (invalidTask) {
    ElMessage.warning(t('adminTemplates.errorTaskItemInvalid'))
    return
  }
  const editingId = props.editingRow?.id ?? null
  emit('submit', {
    ...(editingId != null ? { id: editingId } : {}),
    template_name: form.template_name,
    applicable_levels: form.applicable_levels,
    task_list: taskList as unknown as TemplateItem['task_list'],
    estimated_weeks: form.estimated_weeks,
    status: form.status,
  })
}
</script>

<style scoped>
.hint {
  margin-top: var(--spacing-sm);
  color: var(--text-secondary);
  font-size: var(--font-size-extra-small);
}
</style>

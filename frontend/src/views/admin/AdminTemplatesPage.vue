<template>
  <div class="template-page">
    <BentoCell
      :title="t('adminTemplates.cardTitle')"
      class="template-card bento-item"
    >
      <template #actions>
        <el-button
          type="primary"
          size="small"
          class="magnetic-press"
          @click="openCreate"
        >
          {{ t('adminTemplates.createBtn') }}
        </el-button>
      </template>

      <StatefulContainer
        :loading="loading"
        :empty="!loading && rows.length === 0"
        :error-message="pageError"
        :empty-text="t('adminTemplates.empty')"
        @retry="loadData"
      >
        <el-table
          :data="rows"
          border
          stripe
        >
          <el-table-column
            prop="id"
            :label="t('adminTemplates.colId')"
            width="80"
          />
          <el-table-column
            prop="template_name"
            :label="t('adminTemplates.colTemplateName')"
            min-width="160"
          />
          <el-table-column
            prop="applicable_levels"
            :label="t('adminTemplates.colApplicableLevels')"
            width="160"
          >
            <template #default="{ row }">
              <el-tag
                v-for="lv in row.applicable_levels"
                :key="lv"
                size="small"
                class="level-tag"
              >
                {{ t('adminTemplates.levelTag', { level: lv }) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="estimated_weeks"
            :label="t('adminTemplates.colEstimatedWeeks')"
            width="100"
          >
            <template #default="{ row }">
              {{ row.estimated_weeks ?? '-' }}
            </template>
          </el-table-column>
          <el-table-column
            prop="task_list"
            :label="t('adminTemplates.colTaskCount')"
            width="80"
          >
            <template #default="{ row }">
              {{ row.task_list?.length || 0 }}
            </template>
          </el-table-column>
          <el-table-column
            prop="status"
            :label="t('adminTemplates.colStatus')"
            width="100"
          >
            <template #default="{ row }">
              <el-switch
                v-model="row.status"
                active-value="active"
                inactive-value="inactive"
                :loading="row.statusLoading"
                @change="(val: string | number | boolean) => handleStatusChange(row, val as 'active' | 'inactive')"
              />
            </template>
          </el-table-column>
          <el-table-column
            :label="t('adminTemplates.colOperation')"
            width="220"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                size="small"
                @click="openPreview(row)"
              >
                {{ t('adminTemplates.btnPreview') }}
              </el-button>
              <el-button
                link
                type="primary"
                size="small"
                @click="openEdit(row)"
              >
                {{ t('adminTemplates.btnEdit') }}
              </el-button>
              <!-- ISS-075: 删除模板按钮 -->
              <el-button
                link
                type="danger"
                size="small"
                @click="handleDelete(row)"
              >
                {{ t('adminTemplates.btnDelete') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </StatefulContainer>

      <div class="pager-wrap">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="handlePageChange"
        />
      </div>
    </BentoCell>

    <el-dialog
      v-model="previewVisible"
      :title="t('adminTemplates.previewTitle')"
      width="600px"
      destroy-on-close
    >
      <div
        v-if="previewRow"
        class="preview-content"
      >
        <el-descriptions
          :column="1"
          border
        >
          <el-descriptions-item :label="t('adminTemplates.previewTemplateName')">
            {{ previewRow.template_name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('adminTemplates.previewApplicableLevels')">
            <el-tag
              v-for="lv in previewRow.applicable_levels"
              :key="lv"
              size="small"
              class="level-tag"
            >
              {{ t('adminTemplates.levelTag', { level: lv }) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('adminTemplates.previewEstimatedWeeks')">
            {{ previewRow.estimated_weeks != null ? t('adminTemplates.previewEstimatedWeeksValue', { count: previewRow.estimated_weeks }) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('adminTemplates.previewStatus')">
            <el-tag
              :type="previewRow.status === 'active' ? 'success' : 'info'"
              size="small"
            >
              {{ previewRow.status === 'active' ? t('adminTemplates.statusActive') : t('adminTemplates.statusInactive') }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('adminTemplates.previewTaskList')">
            <div
              v-if="previewRow.task_list?.length"
              class="task-list"
            >
              <div
                v-for="(task, idx) in previewRow.task_list"
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
        <el-button @click="previewVisible = false">
          {{ t('common.close') }}
        </el-button>
        <el-button
          type="primary"
          @click="openEdit(previewRow!); previewVisible = false"
        >
          {{ t('adminTemplates.btnEdit') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="formVisible"
      :title="editingId ? t('adminTemplates.formTitleEdit') : t('adminTemplates.formTitleCreate')"
      width="600px"
      destroy-on-close
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
        <el-button @click="formVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="formSaving"
          @click="submitForm"
        >
          {{ t('common.save') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import BentoCell from '@/components/common/BentoCell.vue'
import { adminApi, type TemplateItem } from '@/api/adminApi'
import { TASK_TYPES, TASK_TYPE_SET, type TaskType } from '@/api/taskTypes'
import { showHttpFeedback } from '@/utils/httpFeedback'

const { t } = useI18n()

const rows = ref<TemplateItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)
const pageError = ref('')

const formVisible = ref(false)
const formSaving = ref(false)
const editingId = ref<number | null>(null)
type TemplateStatus = 'active' | 'inactive'
const form = reactive<{
  template_name: string
  applicable_levels: number[]
  estimated_weeks: number
  status: TemplateStatus
}>({ template_name: '', applicable_levels: [2] as number[], estimated_weeks: 4, status: 'active' as TemplateStatus })
const taskListJson = ref('[]')
const taskListPlaceholder = computed(() => JSON.stringify([
  { task_name: t('adminTemplates.placeholderTaskName'), task_type: 'meditation', schedule: 'daily', duration_minutes: 15 },
], null, 2))
const previewVisible = ref(false)
const previewRow = ref<TemplateItem | null>(null)

const loadData = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const data = await adminApi.listAdminTemplates({ page: page.value, page_size: pageSize.value })
    rows.value = data.items.map((item) => ({
      ...item,
      task_list: (item.task_list ?? []) as TemplateItem['task_list'],
    }))
    total.value = data.total
  } catch (error) {
    pageError.value = showHttpFeedback(error, t('adminTemplates.loadFailed')).detail
  } finally {
    loading.value = false
  }
}

const handlePageChange = (value: number) => {
  page.value = value
  loadData()
}

const openCreate = () => {
  editingId.value = null
  form.template_name = ''
  form.applicable_levels = [2]
  form.estimated_weeks = 4
  form.status = 'active'
  taskListJson.value = '[]'
  formVisible.value = true
}

const openEdit = (row: TemplateItem) => {
  editingId.value = row.id
  form.template_name = row.template_name
  form.applicable_levels = [...row.applicable_levels]
  form.estimated_weeks = row.estimated_weeks ?? 4
  form.status = (row.status as 'active' | 'inactive')
  taskListJson.value = JSON.stringify(row.task_list || [], null, 2)
  formVisible.value = true
}

const openPreview = (row: TemplateItem) => {
  previewRow.value = row
  previewVisible.value = true
}

const handleStatusChange = async (row: TemplateItem & { statusLoading?: boolean }, val: 'active' | 'inactive') => {
  row.statusLoading = true
  try {
    await adminApi.upsertAdminTemplate({
      id: row.id,
      template_name: row.template_name,
      applicable_levels: row.applicable_levels,
      task_list: (row.task_list || []) as unknown as TemplateItem['task_list'],
      estimated_weeks: row.estimated_weeks,
      status: val,
    })
    ElMessage.success(val === 'active' ? t('adminTemplates.templateEnabled') : t('adminTemplates.templateDisabled'))
  } catch (error) {
    row.status = val === 'active' ? 'inactive' : 'active'
    showHttpFeedback(error, t('adminTemplates.statusUpdateFailed'))
  } finally {
    row.statusLoading = false
  }
}

// ISS-075: 删除模板
// ISS-035 修复：删除操作属于不可逆销毁操作，确认框类型由 warning 调整为 error
const handleDelete = async (row: TemplateItem) => {
  try {
    await ElMessageBox.confirm(
      t('adminTemplates.deleteConfirmText', { name: row.template_name }),
      t('adminTemplates.deleteConfirmTitle'),
      { type: 'error', confirmButtonText: t('adminTemplates.deleteConfirmBtn'), cancelButtonText: t('adminTemplates.deleteCancelBtn') }
    )
  } catch {
    return // 用户取消
  }
  try {
    await adminApi.deleteAdminTemplate(row.id)
    ElMessage.success(t('adminTemplates.deleteSuccess'))
    await loadData()
  } catch (error) {
    showHttpFeedback(error, t('adminTemplates.deleteFailed'))
  }
}

const submitForm = async () => {
  if (!form.template_name.trim()) {
    ElMessage.warning(t('adminTemplates.errorTemplateNameRequired'))
    return
  }
  if (!form.applicable_levels.length) {
    ElMessage.warning(t('adminTemplates.errorLevelsRequired'))
    return
  }
  type TaskItem = { task_name: string; task_type: TaskType } & Record<string, unknown>
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
  formSaving.value = true
  try {
    await adminApi.upsertAdminTemplate({
      ...(editingId.value ? { id: editingId.value } : {}),
      template_name: form.template_name,
      applicable_levels: form.applicable_levels,
      task_list: taskList as unknown as TemplateItem['task_list'],
      estimated_weeks: form.estimated_weeks,
      status: form.status,
    })
    formVisible.value = false
    await loadData()
    ElMessage.success(t('adminTemplates.saved'))
  } catch (error) {
    showHttpFeedback(error, t('adminTemplates.saveFailed'))
  } finally {
    formSaving.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.level-tag {
  margin-right: var(--spacing-xs);
}

.hint {
  margin-top: var(--spacing-sm);
  color: var(--text-secondary);
  font-size: var(--font-size-extra-small);
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
  font-size: 11px;
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

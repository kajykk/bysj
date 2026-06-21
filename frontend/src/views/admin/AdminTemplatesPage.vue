<template>
  <div class="template-page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span class="card-title">干预模板管理</span>
          <el-button
            type="primary"
            size="small"
            @click="openCreate"
          >
            新增模板
          </el-button>
        </div>
      </template>

      <StatefulContainer
        :loading="loading"
        :empty="!loading && rows.length === 0"
        :error-message="pageError"
        empty-text="暂无干预模板"
        @retry="loadData"
      >
        <el-table
          :data="rows"
          border
          stripe
        >
          <el-table-column
            prop="id"
            label="ID"
            width="80"
          />
          <el-table-column
            prop="template_name"
            label="模板名称"
            min-width="160"
          />
          <el-table-column
            prop="applicable_levels"
            label="适用等级"
            width="160"
          >
            <template #default="{ row }">
              <el-tag
                v-for="lv in row.applicable_levels"
                :key="lv"
                size="small"
                style="margin-right: 4px"
              >
                等级{{ lv }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="estimated_weeks"
            label="预计周数"
            width="100"
          >
            <template #default="{ row }">
              {{ row.estimated_weeks ?? '-' }}
            </template>
          </el-table-column>
          <el-table-column
            prop="task_list"
            label="任务数"
            width="80"
          >
            <template #default="{ row }">
              {{ row.task_list?.length || 0 }}
            </template>
          </el-table-column>
          <el-table-column
            prop="status"
            label="状态"
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
            label="操作"
            width="180"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                size="small"
                @click="openPreview(row)"
              >
                预览
              </el-button>
              <el-button
                link
                type="primary"
                size="small"
                @click="openEdit(row)"
              >
                编辑
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
    </el-card>

    <el-dialog
      v-model="previewVisible"
      title="模板预览"
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
          <el-descriptions-item label="模板名称">
            {{ previewRow.template_name }}
          </el-descriptions-item>
          <el-descriptions-item label="适用等级">
            <el-tag
              v-for="lv in previewRow.applicable_levels"
              :key="lv"
              size="small"
              style="margin-right: 4px"
            >
              等级{{ lv }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="预计周数">
            {{ previewRow.estimated_weeks ?? '-' }} 周
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag
              :type="previewRow.status === 'active' ? 'success' : 'info'"
              size="small"
            >
              {{ previewRow.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="任务列表">
            <div
              v-if="previewRow.task_list?.length"
              class="task-list"
            >
              <div
                v-for="(task, idx) in previewRow.task_list"
                :key="idx"
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
                >{{ task.duration_minutes }}分钟</span>
              </div>
            </div>
            <span
              v-else
              class="text-muted"
            >暂无任务</span>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">
          关闭
        </el-button>
        <el-button
          type="primary"
          @click="openEdit(previewRow!); previewVisible = false"
        >
          编辑
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="formVisible"
      :title="editingId ? '编辑模板' : '新增模板'"
      width="600px"
      destroy-on-close
    >
      <el-form
        :model="form"
        label-width="100px"
      >
        <el-form-item
          label="模板名称"
          required
        >
          <el-input
            v-model="form.template_name"
            placeholder="请输入模板名称"
          />
        </el-form-item>
        <el-form-item
          label="适用等级"
          required
        >
          <el-select
            v-model="form.applicable_levels"
            multiple
            style="width: 100%"
          >
            <el-option
              label="等级1"
              :value="1"
            />
            <el-option
              label="等级2"
              :value="2"
            />
            <el-option
              label="等级3"
              :value="3"
            />
            <el-option
              label="等级4"
              :value="4"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="预计周数">
          <el-input-number
            v-model="form.estimated_weeks"
            :min="1"
            :max="52"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="form.status"
            style="width: 200px"
          >
            <el-option
              label="启用"
              value="active"
            />
            <el-option
              label="停用"
              value="inactive"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="任务列表">
          <el-input
            v-model="taskListJson"
            type="textarea"
            :rows="6"
            :placeholder="taskListPlaceholder"
          />
          <div class="hint">
            允许的任务类型：{{ TASK_TYPES.join('、') }}
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="formSaving"
          @click="submitForm"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import { adminApi, type TemplateItem } from '@/api/adminApi'
import { TASK_TYPES, TASK_TYPE_SET, type TaskType } from '@/api/taskTypes'
import { showHttpFeedback } from '@/utils/httpFeedback'

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
const taskListPlaceholder = JSON.stringify([
  { task_name: '呼吸训练', task_type: 'meditation', schedule: 'daily', duration_minutes: 15 },
], null, 2)
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
    pageError.value = showHttpFeedback(error, '模板列表加载失败').detail
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
    ElMessage.success(val === 'active' ? '模板已启用' : '模板已停用')
  } catch (error) {
    row.status = val === 'active' ? 'inactive' : 'active'
    showHttpFeedback(error, '状态更新失败')
  } finally {
    row.statusLoading = false
  }
}

const submitForm = async () => {
  if (!form.template_name.trim()) {
    ElMessage.warning('请输入模板名称')
    return
  }
  if (!form.applicable_levels.length) {
    ElMessage.warning('请选择至少一个适用等级')
    return
  }
  type TaskItem = { task_name: string; task_type: TaskType } & Record<string, unknown>
  let taskList: TaskItem[] = []
  try {
    const parsed = JSON.parse(taskListJson.value)
    if (!Array.isArray(parsed)) throw new Error('任务列表必须是数组')
    taskList = parsed as unknown as TaskItem[]
  } catch {
    ElMessage.warning('任务列表 JSON 格式错误，请检查后重试')
    return
  }
  const invalidTask = taskList.find((task) => typeof task.task_name !== 'string' || !TASK_TYPE_SET.has(task.task_type))
  if (invalidTask) {
    ElMessage.warning('任务列表中每项都需要包含 task_name 和合法 task_type')
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
    ElMessage.success('模板已保存')
  } catch (error) {
    showHttpFeedback(error, '保存失败')
  } finally {
    formSaving.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.hint {
  margin-top: 8px;
  color: #909399;
  font-size: 12px;
}

.preview-content {
  padding: 8px 0;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
}

.task-index {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.task-name {
  font-weight: 500;
  color: #303133;
  flex: 1;
}

.task-schedule {
  font-size: 12px;
  color: #909399;
}

.task-duration {
  font-size: 12px;
  color: #606266;
}

.text-muted {
  color: #909399;
  font-size: 13px;
}
</style>

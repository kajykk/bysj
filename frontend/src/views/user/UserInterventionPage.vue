<template>
  <div class="intervention-page">
    <el-tabs
      v-model="activeTab"
      type="border-card"
    >
      <el-tab-pane
        label="当前计划"
        name="active"
      >
        <StatefulContainer
          :loading="activeLoading"
          :empty="!activeLoading && !activeData.plan.id"
          :error-message="activeError"
          empty-text="暂无活跃干预方案，请先完成风险评估"
          @retry="loadActive"
        >
          <template v-if="activeData.plan.id">
            <el-card>
              <template #header>
                <div class="plan-header">
                  <span class="card-title">{{ activeData.plan.plan_name }}</span>
                  <div class="plan-meta">
                    <el-tag
                      :type="riskLevelTag(activeData.plan.risk_level)"
                      size="small"
                    >
                      风险等级 {{ activeData.plan.risk_level }}
                    </el-tag>
                    <span
                      v-if="activeData.plan.start_date"
                      class="plan-date"
                    >开始日期：{{ activeData.plan.start_date }}</span>
                  </div>
                </div>
              </template>
              <div class="progress-wrap">
                <span class="progress-label">总体进度</span>
                <el-progress
                  :percentage="activeData.plan.progress"
                  :stroke-width="16"
                  :text-inside="true"
                />
              </div>
              <div
                v-if="activeData.plan.dominant_modality"
                class="plan-modality"
              >
                主导模态：{{ modalityLabelMap[activeData.plan.dominant_modality] || activeData.plan.dominant_modality }}
              </div>
            </el-card>

            <el-card style="margin-top: 16px">
              <template #header>
                <span class="card-title">今日任务</span>
              </template>
              <div
                v-if="activeData.tasks.length === 0"
                class="text-muted"
              >
                今日暂无任务安排
              </div>
              <div
                v-for="task in activeData.tasks"
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
                  <span class="task-meta">{{ task.schedule === 'daily' ? '每日' : task.schedule === 'weekly' ? '每周' : '一次性' }} · {{ task.duration_minutes }}分钟</span>
                  <div class="task-actions">
                    <el-button
                      v-if="task.today_status === 'pending' || task.today_status === 'postponed'"
                      type="success"
                      size="small"
                      :loading="taskPendingIds.has(task.id) && taskActionType[task.id] === 'complete'"
                      @click="handleComplete(task)"
                    >
                      完成
                    </el-button>
                    <el-button
                      v-if="task.today_status === 'pending' || task.today_status === 'postponed'"
                      size="small"
                      :loading="taskPendingIds.has(task.id) && taskActionType[task.id] === 'skip'"
                      @click="handleSkip(task)"
                    >
                      跳过
                    </el-button>
                    <el-button
                      v-if="task.today_status === 'pending' || task.today_status === 'postponed'"
                      size="small"
                      :loading="taskPendingIds.has(task.id) && taskActionType[task.id] === 'postpone'"
                      @click="openPostpone(task)"
                    >
                      延期
                    </el-button>
                    <el-button
                      v-if="task.today_status === 'completed'"
                      type="primary"
                      size="small"
                      :loading="taskPendingIds.has(task.id) && taskActionType[task.id] === 'feedback'"
                      @click="openFeedback(task)"
                    >
                      反馈
                    </el-button>
                  </div>
                </div>
              </div>
            </el-card>
          </template>
        </StatefulContainer>
      </el-tab-pane>

      <el-tab-pane
        label="历史方案"
        name="history"
      >
        <ListPageScaffold
          title="干预方案历史"
          :loading="historyLoading"
          :empty="!historyLoading && historyRows.length === 0"
          :error-message="historyError"
          empty-text="暂无历史干预方案"
          @retry="loadHistory"
        >
          <PageTable
            :loading="historyLoading"
            :data="historyRows"
            :total="historyTotal"
            :page="historyPage"
            :page-size="historyPageSize"
            @update:page="(v: number) => { historyPage = v; loadHistory() }"
            @update:page-size="(v: number) => { historyPageSize = v; historyPage = 1; loadHistory() }"
          >
            <el-table-column
              prop="plan_id"
              label="ID"
              width="80"
            />
            <el-table-column
              prop="plan_name"
              label="方案名称"
              min-width="180"
            />
            <el-table-column
              prop="status"
              label="状态"
              width="100"
            >
              <template #default="{ row }">
                <el-tag
                  :type="row.status === 'active' ? 'success' : row.status === 'completed' ? 'info' : 'warning'"
                  size="small"
                >
                  {{ row.status === 'active' ? '进行中' : row.status === 'completed' ? '已完成' : row.status === 'cancelled' ? '已取消' : row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="start_date"
              label="开始日期"
              width="120"
            />
            <el-table-column
              prop="end_date"
              label="结束日期"
              width="120"
            >
              <template #default="{ row }">
                {{ row.end_date || '-' }}
              </template>
            </el-table-column>
            <el-table-column
              prop="completion_rate"
              label="完成率"
              width="120"
            >
              <template #default="{ row }">
                <el-progress
                  :percentage="row.completion_rate"
                  :stroke-width="8"
                  :show-text="true"
                />
              </template>
            </el-table-column>
            <el-table-column
              prop="dominant_modality"
              label="主导模态"
              min-width="120"
            >
              <template #default="{ row }">
                {{ row.dominant_modality ? (modalityLabelMap[row.dominant_modality] || row.dominant_modality) : '-' }}
              </template>
            </el-table-column>
          </PageTable>
        </ListPageScaffold>
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="feedbackVisible"
      title="任务反馈"
      width="420px"
      destroy-on-close
    >
      <el-form label-width="80px">
        <el-form-item label="评分">
          <el-rate
            v-model="feedbackForm.score"
            :max="5"
            show-score
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="feedbackForm.note"
            type="textarea"
            :rows="3"
            placeholder="记录你的感受..."
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="feedbackVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="feedbackSubmitting"
          @click="submitFeedback"
        >
          提交
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="postponeVisible"
      title="延期任务"
      width="420px"
      destroy-on-close
    >
      <el-form label-width="80px">
        <el-form-item label="延期至">
          <el-date-picker
            v-model="postponeForm.date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择延期日期"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="postponeForm.note"
            type="textarea"
            :rows="2"
            placeholder="延期原因..."
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="postponeVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="postponeSubmitting"
          :disabled="!postponeForm.date"
          @click="submitPostpone"
        >
          确认延期
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import PageTable from '@/components/common/PageTable.vue'
import { userApi } from '@/api/userApi'
import type { ActiveIntervention, InterventionHistoryItem } from '@/api/userTypes'
import type { InterventionTaskItem } from '@/api/userInterventionApi'
import { normalizeHttpError } from '@/utils/errorPolicy'

const modalityLabelMap: Record<string, string> = {
  structured: '结构化',
  text: '文本',
  physiological: '生理',
  fused: '融合',
  questionnaire: '问卷'
}

const activeTab = ref('active')

const activeData = ref<ActiveIntervention>({
  plan: { id: null, plan_name: '', risk_level: 0, start_date: null, progress: 0 },
  tasks: []
})
const activeLoading = ref(true)
const activeError = ref('')

const taskPendingIds = ref<Set<number>>(new Set())
const taskActionType = ref<Record<number, string>>({})

const setTaskPending = (id: number, action: string, pending: boolean) => {
  const next = new Set(taskPendingIds.value)
  if (pending) {
    next.add(id)
    taskActionType.value = { ...taskActionType.value, [id]: action }
  } else {
    next.delete(id)
  }
  taskPendingIds.value = next
}

const loadActive = async () => {
  activeLoading.value = true
  activeError.value = ''
  try {
    activeData.value = await userApi.getActiveIntervention()
  } catch (error) {
    activeError.value = normalizeHttpError(error, '加载失败').detail
  } finally {
    activeLoading.value = false
  }
}

const riskLevelTag = (level: number) => {
  const map: Record<number, string> = { 0: 'info', 1: 'success', 2: 'warning', 3: 'danger', 4: 'danger' }
  return (map[level] || 'info') as 'info' | 'success' | 'warning' | 'danger'
}

const taskStatusTag = (status: string) => {
  const map: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
    pending: 'info',
    completed: 'success',
    missed: 'danger',
    skipped: 'warning',
    postponed: 'warning'
  }
  return map[status] || 'info'
}

const taskStatusLabel = (status: string) => {
  const map: Record<string, string> = { pending: '待完成', completed: '已完成', missed: '未完成', skipped: '已跳过', postponed: '已延期' }
  return map[status] || status
}

const getTodayDate = () => new Date().toISOString().slice(0, 10)

const handleComplete = async (task: InterventionTaskItem) => {
  try {
    await ElMessageBox.confirm(`确认完成任务「${task.task_name}」？`, '确认', { type: 'success' })
  } catch {
    return
  }
  setTaskPending(task.id, 'complete', true)
  try {
    await userApi.completeInterventionTask(task.id, getTodayDate())
    ElMessage.success('任务已完成')
    await loadActive()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '操作失败').detail)
  } finally {
    setTaskPending(task.id, 'complete', false)
  }
}

const handleSkip = async (task: InterventionTaskItem) => {
  try {
    await ElMessageBox.confirm(`确认跳过任务「${task.task_name}」？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  setTaskPending(task.id, 'skip', true)
  try {
    await userApi.skipInterventionTask(task.id, { scheduled_date: getTodayDate() })
    ElMessage.success('任务已跳过')
    await loadActive()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '操作失败').detail)
  } finally {
    setTaskPending(task.id, 'skip', false)
  }
}

const feedbackVisible = ref(false)
const feedbackSubmitting = ref(false)
const feedbackTaskId = ref(0)
const feedbackForm = reactive({ score: 3, note: '' })

const openFeedback = (task: InterventionTaskItem) => {
  feedbackTaskId.value = task.id
  feedbackForm.score = task.feedback_score || 3
  feedbackForm.note = task.feedback_note || ''
  feedbackVisible.value = true
}

const submitFeedback = async () => {
  feedbackSubmitting.value = true
  try {
    await userApi.feedbackInterventionTask(feedbackTaskId.value, {
      scheduled_date: getTodayDate(),
      feedback_score: feedbackForm.score,
      feedback_note: feedbackForm.note || undefined
    })
    ElMessage.success('反馈已提交')
    feedbackVisible.value = false
    await loadActive()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '提交失败').detail)
  } finally {
    feedbackSubmitting.value = false
  }
}

const postponeVisible = ref(false)
const postponeSubmitting = ref(false)
const postponeTaskId = ref(0)
const postponeForm = reactive({ date: '', note: '' })

const openPostpone = (task: InterventionTaskItem) => {
  postponeTaskId.value = task.id
  postponeForm.date = ''
  postponeForm.note = ''
  postponeVisible.value = true
}

const submitPostpone = async () => {
  if (!postponeForm.date) return
  postponeSubmitting.value = true
  try {
    await userApi.postponeInterventionTask(postponeTaskId.value, {
      scheduled_date: getTodayDate(),
      postpone_to: postponeForm.date,
      note: postponeForm.note || undefined
    })
    ElMessage.success('任务已延期')
    postponeVisible.value = false
    await loadActive()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '延期失败').detail)
  } finally {
    postponeSubmitting.value = false
  }
}

const historyRows = ref<InterventionHistoryItem[]>([])
const historyTotal = ref(0)
const historyPage = ref(1)
const historyPageSize = ref(10)
const historyLoading = ref(false)
const historyError = ref('')

const loadHistory = async () => {
  historyLoading.value = true
  historyError.value = ''
  try {
    const data = await userApi.getInterventionHistory({ page: historyPage.value, page_size: historyPageSize.value })
    historyRows.value = data.items
    historyTotal.value = data.total
  } catch (error) {
    historyError.value = normalizeHttpError(error, '历史记录加载失败').detail
  } finally {
    historyLoading.value = false
  }
}

onMounted(() => {
  loadActive()
  loadHistory()
})
</script>

<style scoped>
.intervention-page {
  padding: 0;
}

.card-title {
  font-weight: 600;
}

.plan-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.plan-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.plan-date {
  font-size: 13px;
  color: #909399;
}

.progress-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
}

.progress-label {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
}

.progress-wrap .el-progress {
  flex: 1;
}

.task-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid #f0f2f5;
}

.task-item:last-child {
  border-bottom: none;
}

.task-left {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex: 1;
}

.task-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.task-name {
  font-weight: 500;
  font-size: 14px;
}

.task-desc {
  font-size: 12px;
  color: #909399;
}

.task-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.task-meta {
  font-size: 12px;
  color: #c0c4cc;
}

.task-actions {
  display: flex;
  gap: 4px;
}

.text-muted {
  color: #909399;
  font-size: 13px;
}
</style>

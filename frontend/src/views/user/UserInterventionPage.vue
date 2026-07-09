<template>
  <div class="intervention-page">
    <el-tabs
      v-model="activeTab"
      type="border-card"
      @tab-change="handleTabChange"
    >
      <el-tab-pane
        :label="t('userIntervention.tabActive')"
        name="active"
      >
        <StatefulContainer
          :loading="activeLoading"
          :empty="!activeLoading && !activeData.plan.id"
          :error-message="activeError"
          :empty-text="t('userIntervention.emptyActive')"
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
                      {{ t('userIntervention.riskLevelLabel') }} {{ activeData.plan.risk_level }}
                    </el-tag>
                    <span
                      v-if="activeData.plan.start_date"
                      class="plan-date"
                    >{{ t('userIntervention.startDatePrefix') }}{{ activeData.plan.start_date }}</span>
                  </div>
                </div>
              </template>
              <div class="progress-wrap">
                <span class="progress-label">{{ t('userIntervention.progressLabel') }}</span>
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
                {{ t('userIntervention.dominantModalityPrefix') }}{{ getModalityLabel(activeData.plan.dominant_modality) }}
              </div>
            </el-card>

            <el-card class="section-card">
              <template #header>
                <span class="card-title">{{ t('userIntervention.todayTasksTitle') }}</span>
              </template>
              <div
                v-if="activeData.tasks.length === 0"
                class="text-muted"
              >
                {{ t('userIntervention.emptyTodayTasks') }}
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
                  <span class="task-meta">{{ getScheduleLabel(task.schedule) }} · {{ task.duration_minutes }}{{ t('userIntervention.durationUnit') }}</span>
                  <div class="task-actions">
                    <el-button
                      v-if="task.today_status === 'pending' || task.today_status === 'postponed'"
                      type="success"
                      size="small"
                      :loading="taskPendingIds.has(task.id) && taskActionType[task.id] === 'complete'"
                      @click="handleComplete(task)"
                    >
                      {{ t('userIntervention.btnComplete') }}
                    </el-button>
                    <el-button
                      v-if="task.today_status === 'pending' || task.today_status === 'postponed'"
                      size="small"
                      :loading="taskPendingIds.has(task.id) && taskActionType[task.id] === 'skip'"
                      @click="handleSkip(task)"
                    >
                      {{ t('userIntervention.btnSkip') }}
                    </el-button>
                    <el-button
                      v-if="task.today_status === 'pending' || task.today_status === 'postponed'"
                      size="small"
                      :loading="taskPendingIds.has(task.id) && taskActionType[task.id] === 'postpone'"
                      @click="openPostpone(task)"
                    >
                      {{ t('userIntervention.btnPostpone') }}
                    </el-button>
                    <el-button
                      v-if="task.today_status === 'completed'"
                      type="primary"
                      size="small"
                      :loading="taskPendingIds.has(task.id) && taskActionType[task.id] === 'feedback'"
                      @click="openFeedback(task)"
                    >
                      {{ t('userIntervention.btnFeedback') }}
                    </el-button>
                  </div>
                </div>
              </div>
            </el-card>
          </template>
        </StatefulContainer>
      </el-tab-pane>

      <el-tab-pane
        :label="t('userIntervention.tabHistory')"
        name="history"
      >
        <ListPageScaffold
          :title="t('userIntervention.historyTitle')"
          :loading="historyLoading"
          :empty="!historyLoading && historyRows.length === 0"
          :error-message="historyError"
          :empty-text="t('userIntervention.emptyHistory')"
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
              :label="t('userIntervention.colId')"
              width="80"
            />
            <el-table-column
              prop="plan_name"
              :label="t('userIntervention.colPlanName')"
              min-width="180"
            />
            <el-table-column
              prop="status"
              :label="t('userIntervention.colStatus')"
              width="100"
            >
              <template #default="{ row }">
                <el-tag
                  :type="row.status === 'active' ? 'success' : row.status === 'completed' ? 'info' : 'warning'"
                  size="small"
                >
                  {{ getHistoryStatusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="start_date"
              :label="t('userIntervention.colStartDate')"
              width="120"
            />
            <el-table-column
              prop="end_date"
              :label="t('userIntervention.colEndDate')"
              width="120"
            >
              <template #default="{ row }">
                {{ row.end_date || '-' }}
              </template>
            </el-table-column>
            <el-table-column
              prop="completion_rate"
              :label="t('userIntervention.colCompletionRate')"
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
              :label="t('userIntervention.colDominantModality')"
              min-width="120"
            >
              <template #default="{ row }">
                {{ row.dominant_modality ? getModalityLabel(row.dominant_modality) : '-' }}
              </template>
            </el-table-column>
          </PageTable>
        </ListPageScaffold>
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="feedbackVisible"
      :title="t('userIntervention.feedbackDialogTitle')"
      width="420px"
      destroy-on-close
    >
      <el-form label-width="80px">
        <el-form-item :label="t('userIntervention.feedbackScoreLabel')">
          <el-rate
            v-model="feedbackForm.score"
            :max="5"
            show-score
          />
        </el-form-item>
        <el-form-item :label="t('userIntervention.feedbackNoteLabel')">
          <el-input
            v-model="feedbackForm.note"
            type="textarea"
            :rows="3"
            :placeholder="t('userIntervention.feedbackNotePlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="feedbackVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="feedbackSubmitting"
          @click="submitFeedback"
        >
          {{ t('userIntervention.btnSubmit') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="postponeVisible"
      :title="t('userIntervention.postponeDialogTitle')"
      width="420px"
      destroy-on-close
    >
      <el-form label-width="80px">
        <el-form-item :label="t('userIntervention.postponeDateLabel')">
          <el-date-picker
            v-model="postponeForm.date"
            type="date"
            value-format="YYYY-MM-DD"
            :placeholder="t('userIntervention.postponeDatePlaceholder')"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="t('userIntervention.feedbackNoteLabel')">
          <el-input
            v-model="postponeForm.note"
            type="textarea"
            :rows="2"
            :placeholder="t('userIntervention.postponeNotePlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="postponeVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="postponeSubmitting"
          :disabled="!postponeForm.date"
          @click="submitPostpone"
        >
          {{ t('userIntervention.btnConfirmPostpone') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import PageTable from '@/components/common/PageTable.vue'
import { userApi } from '@/api/userApi'
import type { ActiveIntervention, InterventionHistoryItem } from '@/api/userTypes'
import type { InterventionTaskItem } from '@/api/userInterventionApi'
import { normalizeHttpError } from '@/utils/errorPolicy'

const { t } = useI18n()

const MODALITY_LABEL_KEYS: Record<string, string> = {
  structured: 'modalityStructured',
  text: 'modalityText',
  physiological: 'modalityPhysiological',
  fused: 'modalityFused',
  questionnaire: 'modalityQuestionnaire'
}
const getModalityLabel = (modality: string | null | undefined) => {
  if (!modality) return ''
  const key = MODALITY_LABEL_KEYS[modality]
  return key ? t(`userIntervention.${key}`) : modality
}

const SCHEDULE_LABEL_KEYS: Record<string, string> = {
  daily: 'scheduleDaily',
  weekly: 'scheduleWeekly',
  once: 'scheduleOnce'
}
const getScheduleLabel = (schedule: string) => {
  const key = SCHEDULE_LABEL_KEYS[schedule]
  return key ? t(`userIntervention.${key}`) : schedule
}

const HISTORY_STATUS_LABEL_KEYS: Record<string, string> = {
  active: 'statusActive',
  completed: 'statusCompleted',
  cancelled: 'statusCancelled'
}
const getHistoryStatusLabel = (status: string) => {
  const key = HISTORY_STATUS_LABEL_KEYS[status]
  return key ? t(`userIntervention.${key}`) : status
}

const TASK_STATUS_LABEL_KEYS: Record<string, string> = {
  pending: 'taskStatusPending',
  completed: 'taskStatusCompleted',
  missed: 'taskStatusMissed',
  skipped: 'taskStatusSkipped',
  postponed: 'taskStatusPostponed'
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
    const data = await userApi.getActiveIntervention()
    activeData.value = {
      plan: {
        id: data.plan.id,
        plan_name: data.plan.plan_name,
        risk_level: data.plan.risk_level,
        start_date: data.plan.start_date,
        progress: data.plan.progress,
        dominant_modality: data.plan.dominant_modality ?? null,
      },
      tasks: data.tasks.map((task) => ({
        id: task.id,
        task_name: task.task_name,
        task_type: task.task_type,
        description: task.description,
        schedule: task.schedule,
        duration_minutes: task.duration_minutes,
        today_status: task.today_status,
        feedback_score: task.feedback_score,
        feedback_note: task.feedback_note,
        modality_based_actions: task.modality_based_actions ?? [],
      })),
    }
  } catch (error) {
    activeError.value = normalizeHttpError(error, t('userIntervention.loadFailed')).detail
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
  const key = TASK_STATUS_LABEL_KEYS[status]
  return key ? t(`userIntervention.${key}`) : status
}

// ISS-016 修复：改用本地日期，避免 toISOString 返回 UTC 日期导致东八区 0-8 点跨日错位
// 'sv-SE' locale 输出 YYYY-MM-DD 格式的本地日期
const getTodayDate = () => new Date().toLocaleDateString('sv-SE')

const handleComplete = async (task: InterventionTaskItem) => {
  try {
    await ElMessageBox.confirm(t('userIntervention.completeConfirm', { name: task.task_name }), t('common.confirm'), { type: 'success' })
  } catch {
    return
  }
  setTaskPending(task.id, 'complete', true)
  try {
    await userApi.completeInterventionTask(task.id, getTodayDate())
    ElMessage.success(t('userIntervention.completeSuccess'))
    await loadActive()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userIntervention.operationFailed')).detail)
  } finally {
    setTaskPending(task.id, 'complete', false)
  }
}

const handleSkip = async (task: InterventionTaskItem) => {
  try {
    await ElMessageBox.confirm(t('userIntervention.skipConfirm', { name: task.task_name }), t('common.confirm'), { type: 'warning' })
  } catch {
    return
  }
  setTaskPending(task.id, 'skip', true)
  try {
    await userApi.skipInterventionTask(task.id, { scheduled_date: getTodayDate() })
    ElMessage.success(t('userIntervention.skipSuccess'))
    await loadActive()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userIntervention.operationFailed')).detail)
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
    ElMessage.success(t('userIntervention.feedbackSuccess'))
    feedbackVisible.value = false
    await loadActive()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userIntervention.submitFailed')).detail)
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
    ElMessage.success(t('userIntervention.postponeSuccess'))
    postponeVisible.value = false
    await loadActive()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userIntervention.postponeFailed')).detail)
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
// ISS-054/061 修复：history tab 改为 lazy 加载，仅在首次激活时拉取，避免 onMounted 并行请求浪费带宽
const historyLoaded = ref(false)

const loadHistory = async () => {
  historyLoading.value = true
  historyError.value = ''
  try {
    const data = await userApi.getInterventionHistory({ page: historyPage.value, page_size: historyPageSize.value })
    historyRows.value = data.items.map((item) => ({
      plan_id: item.plan_id,
      plan_name: item.plan_name,
      status: item.status,
      start_date: item.start_date,
      end_date: item.end_date,
      completion_rate: item.completion_rate,
      risk_change: item.risk_change,
      dominant_modality: item.dominant_modality ?? null,
    }))
    historyTotal.value = data.total
  } catch (error) {
    historyError.value = normalizeHttpError(error, t('userIntervention.historyLoadFailed')).detail
  } finally {
    historyLoading.value = false
  }
}

const handleTabChange = (name: string | number) => {
  // ISS-054/061：切换到 history tab 时首次加载历史数据
  if (name === 'history' && !historyLoaded.value) {
    historyLoaded.value = true
    loadHistory()
  }
}

onMounted(() => {
  loadActive()
})
</script>

<style scoped>
.intervention-page {
  padding: 0;
}

.card-title {
  font-weight: var(--font-weight-semibold);
}

.section-card {
  margin-top: var(--spacing-lg);
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

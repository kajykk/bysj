/**
 * UserIntervention 数据加载与状态管理 composable。
 * 从原 UserInterventionPage.vue 提取所有响应式状态、加载函数与任务操作逻辑，
 * 视图层下沉至 ActivePlanCard / TodayTasksCard / HistoryTab 子组件，
 * 对话框 UI 下沉至 FeedbackDialog / PostponeDialog 子组件。
 */
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { userApi } from '@/api/userApi'
import type { ActiveIntervention, InterventionHistoryItem } from '@/api/userTypes'
import type { InterventionTaskItem } from '@/api/userInterventionApi'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { getTodayDate } from './sharedInterventionUtils'

/** 反馈对话框提交载荷 */
export interface FeedbackSubmitPayload {
  score: number
  note: string
}

/** 推迟对话框提交载荷 */
export interface PostponeSubmitPayload {
  date: string
  note: string
}

export function useInterventionData() {
  const { t } = useI18n()

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

  // 反馈对话框：内部表单状态保留在 composable，initialScore/initialNote 用于打开时回填
  const feedbackVisible = ref(false)
  const feedbackSubmitting = ref(false)
  const feedbackTaskId = ref(0)
  const feedbackInitialScore = ref(3)
  const feedbackInitialNote = ref('')

  const openFeedback = (task: InterventionTaskItem) => {
    feedbackTaskId.value = task.id
    feedbackInitialScore.value = task.feedback_score || 3
    feedbackInitialNote.value = task.feedback_note || ''
    feedbackVisible.value = true
  }

  const submitFeedback = async (payload: FeedbackSubmitPayload) => {
    feedbackSubmitting.value = true
    try {
      await userApi.feedbackInterventionTask(feedbackTaskId.value, {
        scheduled_date: getTodayDate(),
        feedback_score: payload.score,
        feedback_note: payload.note || undefined
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

  // 推迟对话框
  const postponeVisible = ref(false)
  const postponeSubmitting = ref(false)
  const postponeTaskId = ref(0)

  const openPostpone = (task: InterventionTaskItem) => {
    postponeTaskId.value = task.id
    postponeVisible.value = true
  }

  const submitPostpone = async (payload: PostponeSubmitPayload) => {
    if (!payload.date) return
    postponeSubmitting.value = true
    try {
      await userApi.postponeInterventionTask(postponeTaskId.value, {
        scheduled_date: getTodayDate(),
        postpone_to: payload.date,
        note: payload.note || undefined
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

  // 历史记录
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

  const onPageChange = (v: number) => {
    historyPage.value = v
    loadHistory()
  }

  const onPageSizeChange = (v: number) => {
    historyPageSize.value = v
    historyPage.value = 1
    loadHistory()
  }

  onMounted(() => {
    loadActive()
  })

  return {
    activeTab,
    activeData, activeLoading, activeError,
    taskPendingIds, taskActionType,
    loadActive,
    handleComplete, handleSkip,
    feedbackVisible, feedbackSubmitting,
    feedbackInitialScore, feedbackInitialNote,
    openFeedback, submitFeedback,
    postponeVisible, postponeSubmitting,
    openPostpone, submitPostpone,
    historyRows, historyTotal, historyPage, historyPageSize,
    historyLoading, historyError, historyLoaded,
    loadHistory, handleTabChange, onPageChange, onPageSizeChange,
  }
}

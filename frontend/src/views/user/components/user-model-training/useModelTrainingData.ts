/**
 * UserModelTrainingPage 数据加载与状态管理 composable。
 * 从原 UserModelTrainingPage.vue 提取所有响应式状态、加载函数与派生计算属性，
 * 视图层下沉至各子组件。
 */
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { modelApi, type ModelStatusResult } from '@/api/modelApi'
import { useAuthStore } from '@/stores/auth'
import {
  type TrainingLogRow,
  type ActiveJob,
  type TrainingForm,
  POLL_INITIAL_MS,
  POLL_MAX_MS,
} from './sharedModelTrainingUtils'

export function useModelTrainingData() {
  const { t } = useI18n()
  const router = useRouter()
  // ISS-041 修复：引入 auth store 判断角色，仅 admin 可运行训练流水线
  const authStore = useAuthStore()
  const canTrain = computed(() => authStore.role === 'admin')
  const statusLoading = ref(false)
  const modelStatusLoadedAt = ref(t('userModelTraining.notLoaded'))
  const modelStatus = reactive<ModelStatusResult>({
    model_dir: 'models',
    items: [],
    ready: false,
  })
  const modelStatusSummary = reactive({ structured: '—', text: '—' })
  const trainingLogRows = ref<TrainingLogRow[]>([
    { time: new Date().toLocaleString(), stage: 'system', message: t('userModelTraining.initLog'), level: 'info' },
  ])
  const latestLog = computed(() => trainingLogRows.value[0])
  const activeJobId = ref('')
  const activeJob = ref<ActiveJob | null>(null)
  let jobPollTimer: number | undefined
  // ISS-001 修复：训练参数改为表单可配置，epochs 默认 3（原硬编码 epochs=1 几乎无法收敛）
  const trainingForm = reactive<TrainingForm>({
    dataset_name: 'depression_multimodal_v1',
    model_name: 'text_bert_classifier',
    epochs: 3,
    batch_size: 8,
    learning_rate: 2e-5,
  })
  // ISS-002 修复：轮询改为指数退避（初始 5s，最大 30s），原固定 2s 产生大量无效请求
  let pollCurrentMs = POLL_INITIAL_MS

  const pushTrainingLog = (stage: string, message: string, level: TrainingLogRow['level'] = 'info') => {
    trainingLogRows.value.unshift({
      time: new Date().toLocaleString(),
      stage,
      message,
      level,
    })
    trainingLogRows.value = trainingLogRows.value.slice(0, 8)
  }

  const refreshStatus = async () => {
    statusLoading.value = true
    pushTrainingLog('status', t('userModelTraining.logStartRefresh'), 'info')
    try {
      const res = await modelApi.getModelStatus()
      modelStatus.model_dir = res.model_dir
      modelStatus.items = res.items
      modelStatus.ready = res.ready
      modelStatusLoadedAt.value = new Date().toLocaleString()
      modelStatusSummary.structured = res.items.find(i => i.model_id === 'structured_logistic_regression_quick')?.exists ? t('userModelTraining.modelStatusReady') : t('userModelTraining.modelStatusMissing')
      modelStatusSummary.text = res.items.find(i => i.model_id === 'text_depression_model')?.exists && res.items.find(i => i.model_id === 'text_depression_tfidf')?.exists ? t('userModelTraining.modelStatusReady') : t('userModelTraining.modelStatusMissing')
      pushTrainingLog('status', t('userModelTraining.logRefreshComplete', { status: res.ready ? 'READY' : 'PARTIAL' }), res.ready ? 'success' : 'warning')
    } catch {
      ElMessage.warning(t('userModelTraining.loadFailed'))
      pushTrainingLog('status', t('userModelTraining.logLoadFailed'), 'warning')
    } finally {
      statusLoading.value = false
    }
  }

  const stopJobPolling = () => {
    if (jobPollTimer) {
      window.clearTimeout(jobPollTimer)
      jobPollTimer = undefined
    }
  }

  // P2 修复：syncJobState 添加 try/catch 错误处理，避免未处理的 Promise rejection
  const syncJobState = async () => {
    if (!activeJobId.value) return
    try {
      const job = await modelApi.getTrainingJob(activeJobId.value)
      activeJob.value = job
      pushTrainingLog(job.stage || 'job', `${job.message} (${job.progress ?? 0}%)`, job.status === 'failed' ? 'error' : job.status === 'completed' ? 'success' : 'info')
      if (job.status === 'completed' || job.status === 'failed') {
        stopJobPolling()
        if (job.status === 'completed') {
          await refreshStatus()
          pushTrainingLog('train', t('userModelTraining.logTrainComplete'), 'success')
        }
        if (job.status === 'failed') {
          ElMessage.error(job.message || t('userModelTraining.trainFailed'))
        }
      }
    } catch (error) {
      console.error('同步训练任务状态失败', error)
      stopJobPolling()
    }
  }

  const loadLatestJob = async () => {
    try {
      const data = await modelApi.getTrainingJobs()
      const latest = data.jobs?.[0]
      if (!latest) return
      activeJobId.value = latest.job_id || ''
      activeJob.value = latest
      if (latest.job_id) {
        pushTrainingLog(latest.stage || 'job', t('userModelTraining.logFoundJob', { jobId: latest.job_id }), 'info')
        if (latest.status === 'running' || latest.status === 'pending') {
          startJobPolling()
        }
      }
    } catch {
      // ignore training job history load failure
    }
  }

  // ISS-002 修复：指数退避轮询，每次轮询后间隔翻倍，上限 30s
  const startJobPolling = () => {
    stopJobPolling()
    pollCurrentMs = POLL_INITIAL_MS
    const scheduleNext = () => {
      jobPollTimer = window.setTimeout(async () => {
        await syncJobState()
        // 仅在任务仍进行中时继续调度
        if (activeJob.value && (activeJob.value.status === 'running' || activeJob.value.status === 'pending')) {
          pollCurrentMs = Math.min(pollCurrentMs * 2, POLL_MAX_MS)
          scheduleNext()
        }
      }, pollCurrentMs)
    }
    scheduleNext()
  }

  const runTrainingPipeline = async () => {
    statusLoading.value = true
    pushTrainingLog('train', t('userModelTraining.logStartPipeline'), 'info')
    try {
      pushTrainingLog('train', t('userModelTraining.logSubmitJob'), 'info')
      const task = await modelApi.trainModel({
        dataset_name: trainingForm.dataset_name,
        model_name: trainingForm.model_name,
        epochs: trainingForm.epochs,
        batch_size: trainingForm.batch_size,
        learning_rate: trainingForm.learning_rate,
      })
      activeJobId.value = task.job_id || ''
      activeJob.value = task
      pushTrainingLog('train', t('userModelTraining.logJobCreated', { jobId: activeJobId.value || 'unknown' }), 'success')
      startJobPolling()
      await syncJobState()
    } catch (error: unknown) {
      pushTrainingLog('train', t('userModelTraining.logSubmitFailed'), 'error')
      // ISS-041 修复：区分 403 权限错误与其他错误，避免错误归因到"后端服务异常"
      const status = (error as { response?: { status?: number } })?.response?.status
      if (status === 403) {
        ElMessage.error(t('userModelTraining.noPermission'))
      } else {
        ElMessage.error(t('userModelTraining.submitFailedBackend'))
      }
    } finally {
      statusLoading.value = false
    }
  }

  const goToRiskPage = () => {
    pushTrainingLog('nav', t('userModelTraining.logNavToRisk'), 'info')
    router.push('/user/risk')
  }

  const copyModelPaths = async () => {
    const text = [
      'models/artifacts/depression_tabular/best_model.pkl',
      'models/artifacts/text_depression_classifier/text_model.pkl',
      'models/artifacts/text_depression_classifier/text_tfidf.pkl',
    ].join('\n')
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success(t('userModelTraining.pathsCopied'))
      pushTrainingLog('artifact', t('userModelTraining.logPathsCopied'), 'success')
    } catch {
      ElMessage.error(t('userModelTraining.copyFailed'))
      pushTrainingLog('artifact', t('userModelTraining.logCopyFailed'), 'error')
    }
  }

  const openTrainingScript = () => {
    ElMessage.info(t('userModelTraining.runScriptHint'))
    pushTrainingLog('script', t('userModelTraining.logOpenScript'), 'info')
  }

  const scrollToArtifacts = () => {
    ElMessage.success(t('userModelTraining.artifactsShownHint'))
  }

  const showModelStatusDetail = () => {
    // P1-FE-005 修复：移除 dangerouslyUseHTMLString，改为纯文本显示，避免 XSS 风险
    // 使用 \n 换行，配合 customClass 与 CSS white-space: pre-line 实现换行渲染
    // P1-2 角色简化：非 admin 用户不显示 model_id 和 path，仅显示状态摘要
    const validItems = modelStatus.items
      .filter(item => item.lifecycle !== 'deprecated' && item.lifecycle !== 'disabled')
    const lines = canTrain.value
      ? validItems.map(item => `${item.model_id}: ${item.exists ? 'OK' : 'Missing'} ${item.path}`).join('\n')
      : validItems.map(item => `${item.exists ? '✓' : '✗'} ${item.exists ? t('userModelTraining.modelStatusReady') : t('userModelTraining.modelStatusMissing')}`).join('\n')
    // ISS-059 备注：Element Plus 2.x 当前 TypeScript 类型仅声明 customClass，
    // 虽然运行时 class 也能工作，但为了类型安全仍使用 customClass
    ElMessageBox.alert(lines || t('userModelTraining.noModelStatus'), t('userModelTraining.statusDetailTitle'), {
      confirmButtonText: t('common.close'),
      customClass: 'model-status-detail-msgbox',
    })
    pushTrainingLog('status', t('userModelTraining.logOpenStatusDetail'), 'info')
  }

  onMounted(() => {
    refreshStatus()
    void loadLatestJob()
  })

  onUnmounted(() => {
    stopJobPolling()
  })

  return {
    canTrain,
    statusLoading,
    modelStatusLoadedAt,
    modelStatus,
    modelStatusSummary,
    latestLog,
    trainingLogRows,
    activeJobId,
    activeJob,
    trainingForm,
    refreshStatus,
    runTrainingPipeline,
    goToRiskPage,
    copyModelPaths,
    openTrainingScript,
    scrollToArtifacts,
    showModelStatusDetail,
  }
}

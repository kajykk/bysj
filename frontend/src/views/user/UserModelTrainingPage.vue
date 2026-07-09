<template>
  <div class="model-training-page">
    <el-row
      :gutter="16"
      class="top-grid"
    >
      <el-col
        :xs="24"
        :sm="24"
        :md="18"
      >
        <el-card class="hero-card console-card">
          <template #header>
            <div class="header-row">
              <div>
                <div class="eyebrow">
                  {{ t('userModelTraining.trainingConsoleEyebrow') }}
                </div>
                <div class="title">
                  {{ t('userModelTraining.title') }}
                </div>
                <div class="subtitle">
                  {{ t('userModelTraining.subtitle') }}
                </div>
              </div>
              <div class="header-status">
                <el-tag
                  type="success"
                  effect="light"
                >
                  {{ t('userModelTraining.statusReady') }}
                </el-tag>
                <el-tag
                  type="info"
                  effect="plain"
                >
                  {{ t('userModelTraining.dualModal') }}
                </el-tag>
              </div>
            </div>
          </template>

          <el-row
            :gutter="12"
            class="stats-row"
          >
            <el-col :span="8">
              <div class="stat-card accent-blue">
                <div class="stat-label">
                  {{ t('userModelTraining.statStructured') }}
                </div>
                <div class="stat-value">
                  {{ modelStatusSummary.structured }}
                </div>
                <div class="stat-desc">
                  best_model.pkl
                </div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="stat-card accent-green">
                <div class="stat-label">
                  {{ t('userModelTraining.statText') }}
                </div>
                <div class="stat-value">
                  {{ modelStatusSummary.text }}
                </div>
                <div class="stat-desc">
                  text_model.pkl + tfidf.pkl
                </div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="stat-card accent-gold">
                <div class="stat-label">
                  {{ t('userModelTraining.statScript') }}
                </div>
                <div class="stat-value">
                  {{ t('userModelTraining.statScriptValue') }}
                </div>
                <div class="stat-desc">
                  train_ml_oneclick.ps1
                </div>
              </div>
            </el-col>
          </el-row>

          <el-alert
            type="info"
            show-icon
            :closable="false"
            class="console-alert"
            :title="t('userModelTraining.consoleAlert')"
          />

          <el-card
            v-if="activeJob"
            shadow="never"
            class="job-card"
          >
            <template #header>
              <div class="header-row">
                <span class="card-title">{{ t('userModelTraining.activeJobTitle') }}</span>
                <el-tag
                  :type="activeJob.status === 'failed' ? 'danger' : activeJob.status === 'completed' ? 'success' : 'warning'"
                  effect="light"
                >
                  {{ activeJob.status }}
                </el-tag>
              </div>
            </template>
            <el-progress
              :percentage="activeJob.progress || 0"
              :status="activeJob.status === 'failed' ? 'exception' : activeJob.status === 'completed' ? 'success' : undefined"
            />
            <el-descriptions
              :column="3"
              border
              class="job-desc"
            >
              <el-descriptions-item :label="t('userModelTraining.colJobId')">
                {{ activeJob.job_id || activeJobId || '-' }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('userModelTraining.colStage')">
                {{ activeJob.stage || '-' }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('userModelTraining.colMessage')">
                {{ activeJob.message || '-' }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <el-row
            :gutter="16"
            class="action-grid"
          >
            <el-col :span="12">
              <el-card
                shadow="never"
                class="action-card"
              >
                <template #header>
                  <span class="card-title">{{ t('userModelTraining.actionTitle') }}</span>
                </template>
                <div class="action-list">
                  <el-button
                    type="primary"
                    @click="goToRiskPage"
                  >
                    {{ t('userModelTraining.goToRiskBtn') }}
                  </el-button>
                  <el-button @click="copyModelPaths">
                    {{ t('userModelTraining.copyPathsBtn') }}
                  </el-button>
                  <el-button
                    type="success"
                    plain
                    @click="openTrainingScript"
                  >
                    {{ t('userModelTraining.viewScriptBtn') }}
                  </el-button>
                  <el-button
                    :loading="statusLoading"
                    @click="refreshStatus"
                  >
                    {{ t('userModelTraining.refreshBtn') }}
                  </el-button>
                  <el-button
                    v-if="canTrain"
                    type="danger"
                    plain
                    :loading="statusLoading"
                    @click="runTrainingPipeline"
                  >
                    {{ t('userModelTraining.runPipelineBtn') }}
                  </el-button>
                </div>
                <!-- ISS-001 修复：训练参数可配置表单（仅 admin 可见） -->
                <el-form
                  v-if="canTrain"
                  :model="trainingForm"
                  label-width="120px"
                  class="training-form"
                  size="small"
                >
                  <el-form-item :label="t('userModelTraining.formLabelDataset')">
                    <el-input
                      v-model="trainingForm.dataset_name"
                      placeholder="depression_multimodal_v1"
                    />
                  </el-form-item>
                  <el-form-item :label="t('userModelTraining.formLabelModel')">
                    <el-input
                      v-model="trainingForm.model_name"
                      placeholder="text_bert_classifier"
                    />
                  </el-form-item>
                  <el-form-item :label="t('userModelTraining.formLabelEpochs')">
                    <el-input-number
                      v-model="trainingForm.epochs"
                      :min="1"
                      :max="100"
                      :step="1"
                    />
                  </el-form-item>
                  <el-form-item :label="t('userModelTraining.formLabelBatchSize')">
                    <el-input-number
                      v-model="trainingForm.batch_size"
                      :min="1"
                      :max="256"
                      :step="1"
                    />
                  </el-form-item>
                  <el-form-item :label="t('userModelTraining.formLabelLearningRate')">
                    <el-input-number
                      v-model="trainingForm.learning_rate"
                      :min="0"
                      :max="1"
                      :step="0.00001"
                      :precision="6"
                    />
                  </el-form-item>
                </el-form>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card
                shadow="never"
                class="action-card"
              >
                <template #header>
                  <span class="card-title">{{ t('userModelTraining.artifactsTitle') }}</span>
                </template>
                <el-descriptions
                  :column="1"
                  border
                  class="compact-desc"
                >
                  <el-descriptions-item :label="t('userModelTraining.artifactStructured')">
                    models/artifacts/depression_tabular/best_model.pkl
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('userModelTraining.artifactText')">
                    models/artifacts/text_depression_classifier/text_model.pkl
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('userModelTraining.artifactVectorizer')">
                    models/artifacts/text_depression_classifier/text_tfidf.pkl
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('userModelTraining.artifactEntry')">
                    train_ml_oneclick.ps1
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-col>
          </el-row>

          <el-card
            shadow="never"
            class="action-card log-card section-card"
          >
            <template #header>
              <div class="header-row">
                <span class="card-title">{{ t('userModelTraining.logPanelTitle') }}</span>
                <div class="header-status">
                  <el-tag
                    type="info"
                    effect="light"
                  >
                    {{ t('userModelTraining.consoleLog') }}
                  </el-tag>
                  <el-tag
                    v-if="latestLog"
                    :type="latestLog.level === 'error' ? 'danger' : latestLog.level === 'warning' ? 'warning' : 'success'"
                    effect="dark"
                  >
                    {{ t('userModelTraining.latestLog', { stage: latestLog.stage }) }}
                  </el-tag>
                </div>
              </div>
            </template>
            <el-timeline class="training-timeline">
              <el-timeline-item
                v-for="item in trainingLogRows"
                :key="`${item.time}-${item.stage}-${item.message}`"
                :type="item.level === 'error' ? 'danger' : item.level === 'warning' ? 'warning' : 'primary'"
                :timestamp="item.time"
                placement="top"
              >
                <div class="timeline-title">
                  {{ item.stage }}
                </div>
                <div class="timeline-text">
                  {{ item.message }}
                </div>
              </el-timeline-item>
            </el-timeline>
          </el-card>
        </el-card>
      </el-col>

      <el-col
        :xs="24"
        :sm="24"
        :md="6"
      >
        <el-card class="side-card console-side-card">
          <template #header>
            <span class="card-title">{{ t('userModelTraining.hintTitle') }}</span>
          </template>
          <ul class="hint-list">
            <li>{{ t('userModelTraining.hint1') }}</li>
            <li>{{ t('userModelTraining.hint2') }}</li>
            <li>{{ t('userModelTraining.hint3') }}</li>
          </ul>
        </el-card>

        <el-card
          class="side-card console-side-card section-card"
        >
          <template #header>
            <span class="card-title">{{ t('userModelTraining.recentStatusTitle') }}</span>
          </template>
          <div class="status-list">
            <div class="status-item success">
              {{ t('userModelTraining.statusBackend') }}
            </div>
            <div class="status-item success">
              {{ t('userModelTraining.statusFrontend') }}
            </div>
            <div class="status-item info">
              {{ t('userModelTraining.statusEntry') }}
            </div>
            <div class="status-item warning">
              {{ t('userModelTraining.statusAdvice') }}
            </div>
          </div>
          <el-divider />
          <el-descriptions
            :column="1"
            border
            class="compact-desc"
          >
            <el-descriptions-item :label="t('userModelTraining.colModelStatus')">
              {{ modelStatus.ready ? t('userModelTraining.allReady') : t('userModelTraining.partialMissing') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('userModelTraining.colDetectedAt')">
              {{ modelStatusLoadedAt }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('userModelTraining.colModelDir')">
              {{ modelStatus.model_dir }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card
          class="side-card console-side-card section-card"
        >
          <template #header>
            <span class="card-title">{{ t('userModelTraining.shortcutTitle') }}</span>
          </template>
          <el-space
            direction="vertical"
            fill
            style="width: 100%"
          >
            <el-button @click="goToRiskPage">
              {{ t('userModelTraining.riskPanelBtn') }}
            </el-button>
            <el-button @click="scrollToArtifacts">
              {{ t('userModelTraining.artifactsLocationBtn') }}
            </el-button>
            <el-button @click="showModelStatusDetail">
              {{ t('userModelTraining.viewStatusDetailBtn') }}
            </el-button>
          </el-space>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { modelApi, type ModelStatusResult } from '@/api/modelApi'
import { useAuthStore } from '@/stores/auth'

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
const latestLog = computed(() => trainingLogRows.value[0])
const trainingLogRows = ref<Array<{ time: string; stage: string; message: string; level: 'info' | 'warning' | 'success' | 'error' }>>([
  { time: new Date().toLocaleString(), stage: 'system', message: t('userModelTraining.initLog'), level: 'info' },
])
const activeJobId = ref('')
const activeJob = ref<{ job_id?: string; status: string; progress?: number; stage?: string; message: string } | null>(null)
let jobPollTimer: number | undefined
// ISS-001 修复：训练参数改为表单可配置，epochs 默认 3（原硬编码 epochs=1 几乎无法收敛）
const trainingForm = reactive({
  dataset_name: 'depression_multimodal_v1',
  model_name: 'text_bert_classifier',
  epochs: 3,
  batch_size: 8,
  learning_rate: 2e-5,
})
// ISS-002 修复：轮询改为指数退避（初始 5s，最大 30s），原固定 2s 产生大量无效请求
const POLL_INITIAL_MS = 5000
const POLL_MAX_MS = 30000
let pollCurrentMs = POLL_INITIAL_MS

const pushTrainingLog = (stage: string, message: string, level: 'info' | 'warning' | 'success' | 'error' = 'info') => {
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

onUnmounted(() => {
  stopJobPolling()
})

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
  const lines = modelStatus.items
    .filter(item => item.lifecycle !== 'deprecated' && item.lifecycle !== 'disabled')
    .map(item => `${item.model_id}: ${item.exists ? 'OK' : 'Missing'} ${item.path}`).join('\n')
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

</script>

<style scoped>
.model-training-page {
  padding: 0;
}

.top-grid {
  align-items: stretch;
}

.console-card,
.console-side-card,
.hero-card,
.side-card {
  border-radius: 18px;
}

.eyebrow {
  font-size: var(--font-size-extra-small);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.title {
  font-size: var(--font-size-display);
  font-weight: var(--font-weight-bold);
  letter-spacing: var(--letter-spacing-tight);
  line-height: var(--line-height-tight);
  color: var(--text-primary);
}

.subtitle {
  margin-top: 6px;
  color: #6b7280;
  font-size: var(--font-size-small);
}

.header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.header-status {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.stats-row {
  margin-bottom: 16px;
}

.stat-card {
  border-radius: 16px;
  padding: 16px;
  min-height: 106px;
  color: #fff;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

/* ISS-011 修复：改用 CSS 变量定义的渐变令牌，避免硬编码 */
.accent-blue { background: var(--gradient-blue); }
.accent-green { background: var(--gradient-green); }
.accent-gold { background: var(--gradient-gold); }

.stat-label {
  font-size: var(--font-size-extra-small);
  opacity: 0.9;
}

.stat-value {
  margin-top: 8px;
  font-size: var(--font-size-heading);
  font-weight: 800;
}

.stat-desc {
  margin-top: 4px;
  font-size: var(--font-size-extra-small);
  opacity: 0.95;
}

.console-alert {
  margin-bottom: 16px;
}

.section-card {
  margin-top: var(--spacing-lg);
}

.action-grid {
  margin-top: 8px;
}

.action-card {
  min-height: 260px;
  border-radius: 16px;
}

.job-card {
  border-radius: 16px;
  margin-bottom: 16px;
}

.job-desc :deep(.el-descriptions__label) {
  width: 100px;
}

.log-card {
  border-radius: 16px;
}

.training-timeline {
  margin-top: 4px;
}

.timeline-title {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.timeline-text {
  margin-top: 4px;
  color: var(--text-regular);
  line-height: 1.6;
}

.action-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.compact-desc :deep(.el-descriptions__label) {
  width: 120px;
}

.card-title {
  font-weight: var(--font-weight-bold);
}

.hint-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
  color: var(--text-primary);
}

.status-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-item {
  border-radius: 12px;
  padding: 10px 12px;
  font-size: var(--font-size-small);
  line-height: 1.5;
  background: #f8fafc;
  color: #334155;
}

.status-item.success {
  background: var(--success-light);
  color: #2f6b1f;
}

.status-item.info {
  background: var(--info-light);
  color: #205a9d;
}

.status-item.warning {
  background: var(--warning-light);
  color: #8a5a12;
}
</style>

<!-- P1-FE-005 修复：全局样式（非 scoped），用于 ElMessageBox 纯文本换行显示 -->
<style>
.model-status-detail-msgbox .el-messagebox__message {
  white-space: pre-line;
  font-family: monospace;
}
</style>

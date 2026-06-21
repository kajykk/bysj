<template>
  <div class="model-training-page">
    <el-row
      :gutter="16"
      class="top-grid"
    >
      <el-col :span="18">
        <el-card class="hero-card console-card">
          <template #header>
            <div class="header-row">
              <div>
                <div class="eyebrow">
                  Training Console
                </div>
                <div class="title">
                  模型训练控制台
                </div>
                <div class="subtitle">
                  从训练、产物、状态到答辩展示，集中管理当前可用模型。
                </div>
              </div>
              <div class="header-status">
                <el-tag
                  type="success"
                  effect="light"
                >
                  模型就绪
                </el-tag>
                <el-tag
                  type="info"
                  effect="plain"
                >
                  双模态联动
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
                  结构化模型
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
                  文本模型
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
                  训练脚本
                </div>
                <div class="stat-value">
                  1 Click
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
            title="这里用于快速查看训练产物、复制路径、跳转预测页面，并为答辩提供统一展示入口。"
          />

          <el-card
            v-if="activeJob"
            shadow="never"
            class="job-card"
          >
            <template #header>
              <div class="header-row">
                <span class="card-title">当前训练任务</span>
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
              <el-descriptions-item label="任务 ID">
                {{ activeJob.job_id || activeJobId || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="阶段">
                {{ activeJob.stage || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="消息">
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
                  <span class="card-title">训练操作</span>
                </template>
                <div class="action-list">
                  <el-button
                    type="primary"
                    @click="goToRiskPage"
                  >
                    前往风险评估页
                  </el-button>
                  <el-button @click="copyModelPaths">
                    复制模型路径
                  </el-button>
                  <el-button
                    type="success"
                    plain
                    @click="openTrainingScript"
                  >
                    查看一键训练脚本
                  </el-button>
                  <el-button
                    :loading="statusLoading"
                    @click="refreshStatus"
                  >
                    刷新模型状态
                  </el-button>
                  <el-button
                    type="danger"
                    plain
                    :loading="statusLoading"
                    @click="runTrainingPipeline"
                  >
                    运行训练流水线
                  </el-button>
                </div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card
                shadow="never"
                class="action-card"
              >
                <template #header>
                  <span class="card-title">模型产物</span>
                </template>
                <el-descriptions
                  :column="1"
                  border
                  class="compact-desc"
                >
                  <el-descriptions-item label="结构化模型">
                    models/artifacts/depression_tabular/best_model.pkl
                  </el-descriptions-item>
                  <el-descriptions-item label="文本模型">
                    models/artifacts/text_depression_classifier/text_model.pkl
                  </el-descriptions-item>
                  <el-descriptions-item label="文本向量器">
                    models/artifacts/text_depression_classifier/text_tfidf.pkl
                  </el-descriptions-item>
                  <el-descriptions-item label="训练入口">
                    train_ml_oneclick.ps1
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-col>
          </el-row>

          <el-card
            shadow="never"
            class="action-card log-card"
            style="margin-top: 16px"
          >
            <template #header>
              <div class="header-row">
                <span class="card-title">训练日志面板</span>
                <div class="header-status">
                  <el-tag
                    type="info"
                    effect="light"
                  >
                    Console Log
                  </el-tag>
                  <el-tag
                    v-if="latestLog"
                    :type="latestLog.level === 'error' ? 'danger' : latestLog.level === 'warning' ? 'warning' : 'success'"
                    effect="dark"
                  >
                    最近：{{ latestLog.stage }}
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

      <el-col :span="6">
        <el-card class="side-card console-side-card">
          <template #header>
            <span class="card-title">运行说明</span>
          </template>
          <ul class="hint-list">
            <li>先执行一键训练脚本，再刷新页面查看最新状态。</li>
            <li>结构化预测和文本预测已自动读取新模型。</li>
            <li>答辩时可以直接从这里跳转到风险评估页演示。</li>
          </ul>
        </el-card>

        <el-card
          class="side-card console-side-card"
          style="margin-top: 16px"
        >
          <template #header>
            <span class="card-title">最近状态</span>
          </template>
          <div class="status-list">
            <div class="status-item success">
              后端预测：已切换到新模型路径
            </div>
            <div class="status-item success">
              前端展示：已适配新训练模型
            </div>
            <div class="status-item info">
              训练入口：已加入侧边菜单
            </div>
            <div class="status-item warning">
              建议：训练后先检查风险页展示效果
            </div>
          </div>
          <el-divider />
          <el-descriptions
            :column="1"
            border
            class="compact-desc"
          >
            <el-descriptions-item label="模型状态">
              {{ modelStatus.ready ? '全部就绪' : '部分缺失' }}
            </el-descriptions-item>
            <el-descriptions-item label="检测时间">
              {{ modelStatusLoadedAt }}
            </el-descriptions-item>
            <el-descriptions-item label="模型目录">
              {{ modelStatus.model_dir }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card
          class="side-card console-side-card"
          style="margin-top: 16px"
        >
          <template #header>
            <span class="card-title">快捷入口</span>
          </template>
          <el-space
            direction="vertical"
            fill
            style="width: 100%"
          >
            <el-button @click="goToRiskPage">
              风险评估面板
            </el-button>
            <el-button @click="scrollToArtifacts">
              模型产物位置
            </el-button>
            <el-button @click="showModelStatusDetail">
              查看模型状态详情
            </el-button>
          </el-space>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { modelApi, type ModelStatusResult } from '@/api/modelApi'

const router = useRouter()
const statusLoading = ref(false)
const modelStatusLoadedAt = ref('未加载')
const modelStatus = reactive<ModelStatusResult>({
  model_dir: 'models',
  items: [],
  ready: false,
})
const modelStatusSummary = reactive({ structured: '—', text: '—' })
const latestLog = computed(() => trainingLogRows.value[0])
const trainingLogRows = ref<Array<{ time: string; stage: string; message: string; level: 'info' | 'warning' | 'success' | 'error' }>>([
  { time: new Date().toLocaleString(), stage: 'system', message: '训练控制台已初始化，等待模型状态刷新', level: 'info' },
])
const activeJobId = ref('')
const activeJob = ref<{ job_id?: string; status: string; progress?: number; stage?: string; message: string } | null>(null)
let jobPollTimer: number | undefined

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
  pushTrainingLog('status', '开始刷新模型状态', 'info')
  try {
    const res = await modelApi.getModelStatus()
    modelStatus.model_dir = res.model_dir
    modelStatus.items = res.items
    modelStatus.ready = res.ready
    modelStatusLoadedAt.value = new Date().toLocaleString()
    modelStatusSummary.structured = res.items.find(i => i.model_id === 'structured_logistic_regression_quick')?.exists ? 'Ready' : 'Missing'
    modelStatusSummary.text = res.items.find(i => i.model_id === 'text_depression_model')?.exists && res.items.find(i => i.model_id === 'text_depression_tfidf')?.exists ? 'Ready' : 'Missing'
    pushTrainingLog('status', `模型状态刷新完成，整体状态：${res.ready ? 'READY' : 'PARTIAL'}`, res.ready ? 'success' : 'warning')
  } catch {
    ElMessage.warning('模型状态加载失败，已使用本地默认展示')
    pushTrainingLog('status', '模型状态加载失败，使用本地默认展示', 'warning')
  } finally {
    statusLoading.value = false
  }
}

const stopJobPolling = () => {
  if (jobPollTimer) {
    window.clearInterval(jobPollTimer)
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
        pushTrainingLog('train', '训练完成并刷新模型状态', 'success')
      }
      if (job.status === 'failed') {
        ElMessage.error(job.message || '训练任务失败')
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
      pushTrainingLog(latest.stage || 'job', `发现最近训练任务：${latest.job_id}`, 'info')
      if (latest.status === 'running' || latest.status === 'pending') {
        startJobPolling()
      }
    }
  } catch {
    // ignore training job history load failure
  }
}

const startJobPolling = () => {
  stopJobPolling()
  jobPollTimer = window.setInterval(() => {
    void syncJobState()
  }, 2000)
}

const runTrainingPipeline = async () => {
  statusLoading.value = true
  pushTrainingLog('train', '开始执行训练流水线', 'info')
  try {
    pushTrainingLog('train', '提交训练任务', 'info')
    const task = await modelApi.trainModel({ dataset_name: 'depression_multimodal_v1', model_name: 'text_bert_classifier', epochs: 1, batch_size: 8, learning_rate: 2e-5 })
    activeJobId.value = task.job_id || ''
    activeJob.value = task
    pushTrainingLog('train', `任务已创建：${activeJobId.value || 'unknown'}`, 'success')
    startJobPolling()
    await syncJobState()
  } catch (error) {
    pushTrainingLog('train', '训练任务提交失败', 'error')
    ElMessage.error('训练任务提交失败，请检查后端训练服务')
  } finally {
    statusLoading.value = false
  }
}

onUnmounted(() => {
  stopJobPolling()
})

const goToRiskPage = () => {
  pushTrainingLog('nav', '跳转到风险评估页', 'info')
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
    ElMessage.success('模型路径已复制')
    pushTrainingLog('artifact', '模型路径已复制到剪贴板', 'success')
  } catch {
    ElMessage.error('复制失败')
    pushTrainingLog('artifact', '复制模型路径失败', 'error')
  }
}

const openTrainingScript = () => {
  ElMessage.info('请在项目根目录运行 train_ml_oneclick.ps1')
  pushTrainingLog('script', '提示打开一键训练脚本', 'info')
}

const scrollToArtifacts = () => {
  ElMessage.success('模型产物已在页面中展示，可直接复制路径')
}

const showModelStatusDetail = () => {
  // P1-FE-005 修复：移除 dangerouslyUseHTMLString，改为纯文本显示，避免 XSS 风险
  // 使用 \n 换行，配合 customClass 与 CSS white-space: pre-line 实现换行渲染
  const lines = modelStatus.items
    .filter(item => item.lifecycle !== 'deprecated' && item.lifecycle !== 'disabled')
    .map(item => `${item.model_id}: ${item.exists ? 'OK' : 'Missing'} ${item.path}`).join('\n')
  ElMessageBox.alert(lines || '暂无模型状态', '模型状态详情', {
    confirmButtonText: '关闭',
    customClass: 'model-status-detail-msgbox',
  })
  pushTrainingLog('status', '打开模型状态详情面板', 'info')
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
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #909399;
  margin-bottom: 4px;
}

.title {
  font-size: 24px;
  font-weight: 800;
  color: #1f2937;
}

.subtitle {
  margin-top: 6px;
  color: #6b7280;
  font-size: 13px;
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

.accent-blue { background: linear-gradient(135deg, #409eff, #6aa9ff); }
.accent-green { background: linear-gradient(135deg, #67c23a, #88d36e); }
.accent-gold { background: linear-gradient(135deg, #e6a23c, #f2bb63); }

.stat-label {
  font-size: 12px;
  opacity: 0.9;
}

.stat-value {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 800;
}

.stat-desc {
  margin-top: 4px;
  font-size: 12px;
  opacity: 0.95;
}

.console-alert {
  margin-bottom: 16px;
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
  font-weight: 600;
  color: #303133;
}

.timeline-text {
  margin-top: 4px;
  color: #606266;
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
  font-weight: 700;
}

.hint-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
  color: #303133;
}

.status-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-item {
  border-radius: 12px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.5;
  background: #f8fafc;
  color: #334155;
}

.status-item.success {
  background: rgba(103, 194, 58, 0.12);
  color: #2f6b1f;
}

.status-item.info {
  background: rgba(64, 158, 255, 0.12);
  color: #205a9d;
}

.status-item.warning {
  background: rgba(230, 162, 60, 0.14);
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

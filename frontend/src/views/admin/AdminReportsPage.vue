<!-- frontend/src/views/admin/AdminReportsPage.vue -->
<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { reportsApi, type ReportTemplate, type PdfJobItem, type UserRiskReportRequest } from '@/api/reportsApi'
import { showHttpFeedback } from '@/utils/httpFeedback'

const { t } = useI18n()
const templates = ref<ReportTemplate[]>([])
const jobs = ref<PdfJobItem[]>([])
const pdfForm = ref<UserRiskReportRequest>({ user_id: 0, user_name: '', risk_level: 1, risk_trend: 'stable', recommendations: [] })
const generating = ref(false)
const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null)
const currentJob = ref<{ job_id: string; status: string; progress: number } | null>(null)
const excelInput = ref('[]')
const excelCols = ref<string[]>([])
const excelFilename = ref('batch-export.xlsx')

function isTerminalStatus(status: string): boolean {
  return status === 'completed' || status === 'failed'
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function loadTemplates() {
  try {
    const res = await reportsApi.listReportTemplates()
    templates.value = res.templates
  } catch (e) { showHttpFeedback(e, t('common.loadFailed')) }
}

async function loadJobs() {
  try {
    const res = await reportsApi.listPdfJobs()
    jobs.value = res.jobs
  } catch (e) { showHttpFeedback(e, t('common.loadFailed')) }
}

function stopPolling() {
  if (pollingTimer.value) { clearInterval(pollingTimer.value); pollingTimer.value = null }
}

async function pollJobStatus(jobId: string) {
  try {
    const s = await reportsApi.getPdfJobStatus(jobId)
    currentJob.value = { job_id: jobId, status: s.status, progress: s.progress }
    if (isTerminalStatus(s.status)) {
      stopPolling()
      if (s.status === 'completed') ElMessage.success(t('reports.pdfReady'))
      await loadJobs()
    }
  } catch (e) { stopPolling(); showHttpFeedback(e, t('common.loadFailed')) }
}

function startPolling(jobId: string) {
  stopPolling()
  pollingTimer.value = setInterval(() => pollJobStatus(jobId), 2000)
}

async function generateSync() {
  generating.value = true
  try {
    const blob = await reportsApi.generateUserRiskPdfSync(pdfForm.value)
    triggerBlobDownload(blob, `user-risk-${pdfForm.value.user_id}.pdf`)
    ElMessage.success(t('common.exportSuccess'))
  } catch (e) { showHttpFeedback(e, t('common.exportFailed')) }
  finally { generating.value = false }
}

async function generateAsync() {
  generating.value = true
  try {
    const res = await reportsApi.generateUserRiskPdfAsync(pdfForm.value)
    currentJob.value = { job_id: res.job_id, status: res.status, progress: 0 }
    startPolling(res.job_id)
    ElMessage.info(t('reports.pdfGenerating'))
  } catch (e) { showHttpFeedback(e, t('common.exportFailed')) }
  finally { generating.value = false }
}

async function downloadJob(jobId: string) {
  try {
    const blob = await reportsApi.downloadPdf(jobId)
    triggerBlobDownload(blob, `${jobId}.pdf`)
  } catch (e) { showHttpFeedback(e, t('common.exportFailed')) }
}

function validateBatchExcelInput(raw: string): { ok: boolean; data?: unknown[]; error?: string } {
  let parsed: unknown
  try { parsed = JSON.parse(raw) } catch { return { ok: false, error: 'JSON 解析失败' } }
  if (!Array.isArray(parsed)) return { ok: false, error: 'data 必须为数组' }
  if (parsed.length > 1000) return { ok: false, error: 'data 最多 1000 行' }
  return { ok: true, data: parsed as unknown[] }
}

async function exportExcel() {
  const v = validateBatchExcelInput(excelInput.value)
  if (!v.ok) { ElMessage.warning(v.error || ''); return }
  if (excelCols.value.length > 50) { ElMessage.warning('columns 最多 50 列'); return }
  try {
    const blob = await reportsApi.batchExportExcel({ data: v.data as Record<string, unknown>[], columns: excelCols.value, filename: excelFilename.value })
    triggerBlobDownload(blob, excelFilename.value)
    ElMessage.success(t('common.exportSuccess'))
  } catch (e) { showHttpFeedback(e, t('common.exportFailed')) }
}

onMounted(() => { loadTemplates(); loadJobs() })
onUnmounted(stopPolling)
</script>

<template>
  <div class="admin-reports-page">
    <el-card class="templates-card">
      <template #header>{{ t('reports.templates') }}</template>
      <el-row :gutter="12">
        <el-col v-for="tp in templates" :key="tp.name" :span="6">
          <el-card shadow="hover">
            <h4>{{ tp.name }}</h4>
            <p>{{ tp.description }}</p>
            <el-tag size="small">{{ tp.format }}</el-tag>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <el-card class="pdf-card">
      <template #header>{{ t('reports.generatePdf') }}</template>
      <el-form :model="pdfForm" label-width="120px">
        <el-form-item label="user_id"><el-input-number v-model="pdfForm.user_id" :min="1" /></el-form-item>
        <el-form-item label="user_name"><el-input v-model="pdfForm.user_name" /></el-form-item>
        <el-form-item label="risk_level"><el-input-number v-model="pdfForm.risk_level" :min="0" :max="4" /></el-form-item>
        <el-form-item label="risk_trend"><el-input v-model="pdfForm.risk_trend" /></el-form-item>
        <el-form-item label="recommendations">
          <el-input v-model="(pdfForm.recommendations as unknown as string)" type="textarea" placeholder="逗号分隔" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="generating" @click="generateSync">{{ t('reports.syncGenerate') }}</el-button>
          <el-button :loading="generating" @click="generateAsync">{{ t('reports.asyncGenerate') }}</el-button>
        </el-form-item>
      </el-form>
      <el-progress v-if="currentJob" :percentage="currentJob.progress" :status="currentJob.status === 'failed' ? 'exception' : 'success'" />
      <el-button v-if="currentJob?.status === 'completed'" type="success" @click="downloadJob(currentJob.job_id)">{{ t('common.download') }}</el-button>
    </el-card>

    <el-card class="jobs-card">
      <template #header>{{ t('reports.jobList') }}</template>
      <el-table :data="jobs" stripe>
        <el-table-column prop="job_id" label="job_id" />
        <el-table-column prop="status" label="status" />
        <el-table-column prop="progress" label="progress">
          <template #default="{ row }"><el-progress :percentage="row.progress" /></template>
        </el-table-column>
        <el-table-column prop="created_at" label="created_at" />
        <el-table-column label="操作">
          <template #default="{ row }">
            <el-button v-if="row.status === 'completed'" size="small" type="success" @click="downloadJob(row.job_id)">{{ t('common.download') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="excel-card">
      <template #header>{{ t('reports.batchExcel') }}</template>
      <el-input v-model="excelInput" type="textarea" :rows="6" placeholder='[{"col":"val"}]' />
      <el-input v-model="(excelCols as unknown as string)" placeholder="col1,col2（逗号分隔，最多 50 列）" style="margin-top: 8px" />
      <el-input v-model="excelFilename" placeholder="filename.xlsx" style="margin-top: 8px" />
      <el-button type="primary" style="margin-top: 8px" @click="exportExcel">{{ t('common.export') }}</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.admin-reports-page { display: flex; flex-direction: column; gap: 16px; }
</style>

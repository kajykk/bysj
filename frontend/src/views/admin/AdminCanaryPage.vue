<!-- frontend/src/views/admin/AdminCanaryPage.vue -->
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { canaryApi, type CanaryDeployment, type CanaryCreateRequest } from '@/api/canaryApi'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { availableActions } from './utils/canaryUtils'

const { t } = useI18n()
const deployments = ref<CanaryDeployment[]>([])
const percentages = ref<number[]>([])
const loading = ref(false)
const createVisible = ref(false)
const createForm = ref<CanaryCreateRequest>({ version: '', traffic_percent: 1 })
const trafficVisible = ref(false)
const trafficTarget = ref<{ id: number; percent: number } | null>(null)

const runningCount = computed(() => deployments.value.filter((d) => d.status === 'running').length)
const pausedCount = computed(() => deployments.value.filter((d) => d.status === 'paused').length)

async function loadAll() {
  loading.value = true
  try {
    const [list, pct] = await Promise.all([canaryApi.listCanaryDeployments(), canaryApi.getCanaryTrafficPercentages()])
    deployments.value = list.items
    percentages.value = pct.percentages
  } catch (e) { showHttpFeedback(e, t('common.loadFailed')) }
  finally { loading.value = false }
}

async function createDeployment() {
  if (!createForm.value.version.trim()) { ElMessage.warning('version 必填'); return }
  try {
    await canaryApi.createCanaryDeployment(createForm.value)
    ElMessage.success(t('common.createSuccess'))
    createVisible.value = false
    createForm.value = { version: '', traffic_percent: 1 }
    await loadAll()
  } catch (e) { showHttpFeedback(e, t('common.createFailed')) }
}

function openTrafficDialog(d: CanaryDeployment) {
  trafficTarget.value = { id: d.id, percent: d.traffic_percent }
  trafficVisible.value = true
}

async function updateTraffic() {
  if (!trafficTarget.value) return
  const p = trafficTarget.value.percent
  if (p < 1 || p > 100) { ElMessage.warning('范围 1-100'); return }
  try {
    await canaryApi.updateCanaryTraffic(trafficTarget.value.id, { traffic_percent: p })
    ElMessage.success(t('common.updateSuccess'))
    trafficVisible.value = false
    await loadAll()
  } catch (e) { showHttpFeedback(e, t('common.updateFailed')) }
}

async function pauseDeployment(d: CanaryDeployment) {
  try { await canaryApi.pauseCanary(d.id); ElMessage.success(t('common.success')); await loadAll() }
  catch (e) { showHttpFeedback(e, t('common.failed')) }
}

async function resumeDeployment(d: CanaryDeployment) {
  try { await canaryApi.resumeCanary(d.id); ElMessage.success(t('common.success')); await loadAll() }
  catch (e) { showHttpFeedback(e, t('common.failed')) }
}

async function completeDeployment(d: CanaryDeployment) {
  try {
    await ElMessageBox.confirm(t('canary.confirmComplete', { v: d.version }), t('common.confirm'), { type: 'warning' })
    await canaryApi.completeCanary(d.id); ElMessage.success(t('common.success')); await loadAll()
  } catch (e) { if (e !== 'cancel') showHttpFeedback(e, t('common.failed')) }
}

async function rollbackDeployment(d: CanaryDeployment) {
  try {
    const { value } = await ElMessageBox.prompt(t('canary.rollbackReason'), t('canary.rollback'), { type: 'error', inputType: 'textarea', inputValidator: (v) => (v && v.trim().length >= 1 && v.length <= 500) || t('canary.reasonRequired') })
    await canaryApi.rollbackCanary(d.id, { reason: value })
    ElMessage.success(t('common.success')); await loadAll()
  } catch (e) { if (e !== 'cancel') showHttpFeedback(e, t('common.failed')) }
}

onMounted(loadAll)
</script>

<template>
  <div v-loading="loading" class="canary-page">
    <div class="toolbar">
      <span>{{ t('canary.running') }}: {{ runningCount }}</span>
      <span>{{ t('canary.paused') }}: {{ pausedCount }}</span>
      <el-button type="primary" @click="createVisible = true">{{ t('canary.newDeployment') }}</el-button>
      <el-button @click="loadAll">{{ t('common.refresh') }}</el-button>
    </div>
    <el-table :data="deployments" stripe>
      <el-table-column prop="version" label="version" />
      <el-table-column prop="traffic_percent" label="traffic %" />
      <el-table-column prop="status" label="status" />
      <el-table-column prop="started_at" label="started_at" />
      <el-table-column :label="t('common.actions')">
        <template #default="{ row }">
          <el-button v-if="availableActions(row.status).includes('adjust')" size="small" @click="openTrafficDialog(row)">{{ t('canary.adjustTraffic') }}</el-button>
          <el-button v-if="availableActions(row.status).includes('pause')" size="small" @click="pauseDeployment(row)">{{ t('canary.pause') }}</el-button>
          <el-button v-if="availableActions(row.status).includes('resume')" size="small" @click="resumeDeployment(row)">{{ t('canary.resume') }}</el-button>
          <el-button v-if="availableActions(row.status).includes('complete')" size="small" type="success" @click="completeDeployment(row)">{{ t('canary.complete') }}</el-button>
          <el-button v-if="availableActions(row.status).includes('rollback')" size="small" type="danger" @click="rollbackDeployment(row)">{{ t('canary.rollback') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createVisible" :title="t('canary.newDeployment')" width="40%">
      <el-form label-width="120px">
        <el-form-item label="version"><el-input v-model="createForm.version" /></el-form-item>
        <el-form-item label="traffic %">
          <el-select v-model="createForm.traffic_percent">
            <el-option v-for="p in percentages" :key="p" :label="p + '%'" :value="p" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="createVisible = false">{{ t('common.cancel') }}</el-button><el-button type="primary" @click="createDeployment">{{ t('common.confirm') }}</el-button></template>
    </el-dialog>

    <el-dialog v-model="trafficVisible" :title="t('canary.adjustTraffic')" width="30%">
      <el-slider v-model="trafficTarget.percent" :min="1" :max="100" :marks="Object.fromEntries(percentages.map((p) => [p, p + '%']))" />
      <template #footer><el-button @click="trafficVisible = false">{{ t('common.cancel') }}</el-button><el-button type="primary" @click="updateTraffic">{{ t('common.confirm') }}</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.canary-page { display: flex; flex-direction: column; gap: 12px; }
.toolbar { display: flex; gap: 16px; align-items: center; }
</style>

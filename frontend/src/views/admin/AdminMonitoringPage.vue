<!-- frontend/src/views/admin/AdminMonitoringPage.vue -->
<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { monitoringApi, type MonitoringSummary, type RequestDetailsList, type RequestDetailItem } from '@/api/monitoringApi'
import { showHttpFeedback } from '@/utils/httpFeedback'
import BaseChart from '@/components/charts/BaseChart.vue'
import type { EChartsCoreOption } from '@/utils/echarts'
import { maskSensitive } from './utils/monitoringUtils'

const { t } = useI18n()

const summary = ref<MonitoringSummary | null>(null)
const successRate = ref<{ rate: number; points?: unknown[] } | null>(null)
const fallbackStats = ref<{ count: number } | null>(null)
const driftAlerts = ref<{ items: unknown[] } | null>(null)
const engineSnapshot = ref<{ engines: unknown[] } | null>(null)
const details = ref<RequestDetailsList | null>(null)
const detailRow = ref<RequestDetailItem | null>(null)
const detailVisible = ref(false)
const page = reactive({ limit: 20, offset: 0 })
const autoRefresh = ref(false)
const refreshTimer = ref<ReturnType<typeof setInterval> | null>(null)
const loading = ref(false)

const successOption = computed<EChartsCoreOption>(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: (successRate.value?.points as { date?: string }[] || []).map((p) => p.date || '') },
  yAxis: { type: 'value', max: 1 },
  series: [{ type: 'line', data: (successRate.value?.points as { rate?: number }[] || []).map((p) => p.rate || 0), smooth: true }],
}))

async function loadAll() {
  loading.value = true
  const results = await Promise.allSettled([
    monitoringApi.getDashboardSummary(),
    monitoringApi.getModelSuccessRate(),
    monitoringApi.getFallbackStats(),
    monitoringApi.getDriftAlerts(),
    monitoringApi.getEngineSnapshot(),
    monitoringApi.getRequestDetailsList(page),
  ])
  if (results[0].status === 'fulfilled') summary.value = results[0].value
  if (results[1].status === 'fulfilled') successRate.value = results[1].value
  if (results[2].status === 'fulfilled') fallbackStats.value = results[2].value
  if (results[3].status === 'fulfilled') driftAlerts.value = results[3].value
  if (results[4].status === 'fulfilled') engineSnapshot.value = results[4].value
  if (results[5].status === 'fulfilled') details.value = results[5].value
  loading.value = false
}

async function loadDetails() {
  try { details.value = await monitoringApi.getRequestDetailsList(page) }
  catch (e) { showHttpFeedback(e, t('common.loadFailed')) }
}

async function showDetail(logId: string) {
  try { detailRow.value = await monitoringApi.getRequestDetail(logId); detailVisible.value = true }
  catch (e) { showHttpFeedback(e, t('common.loadFailed')) }
}

function onPageChange(p: number) {
  page.offset = (p - 1) * page.limit
  loadDetails()
}

function toggleAutoRefresh(val: boolean) {
  if (val) refreshTimer.value = setInterval(loadAll, 30000)
  else if (refreshTimer.value) { clearInterval(refreshTimer.value); refreshTimer.value = null }
}

onMounted(loadAll)
onUnmounted(() => { if (refreshTimer.value) clearInterval(refreshTimer.value) })
</script>

<template>
  <div v-loading="loading" class="monitoring-page">
    <div class="toolbar">
      <el-button @click="loadAll">{{ t('common.refresh') }}</el-button>
      <el-switch v-model="autoRefresh" @change="toggleAutoRefresh" :active-text="t('common.autoRefresh')" />
    </div>
    <el-row :gutter="12">
      <el-col :span="6"><el-card><template #header>{{ t('monitoring.totalRequests') }}</template>{{ summary?.total_requests }}</el-card></el-col>
      <el-col :span="6"><el-card><template #header>{{ t('monitoring.fallbackCount') }}</template>{{ fallbackStats?.count }}</el-card></el-col>
      <el-col :span="6"><el-card><template #header>{{ t('monitoring.driftAlerts') }}</template>{{ driftAlerts?.items?.length }}</el-card></el-col>
      <el-col :span="6"><el-card><template #header>{{ t('monitoring.engines') }}</template>{{ engineSnapshot?.engines?.length }}</el-card></el-col>
    </el-row>
    <el-card><template #header>{{ t('monitoring.modelSuccessRate') }}</template><BaseChart :option="successOption" height="280px" /></el-card>
    <el-card>
      <template #header>{{ t('monitoring.requestDetails') }}</template>
      <el-table :data="details?.items || []" stripe @row-click="(row: RequestDetailItem) => showDetail(row.log_id)">
        <el-table-column prop="log_id" :label="t('monitoring.logId')" width="180" />
        <el-table-column :label="t('monitoring.input')">
          <template #default="{ row }">{{ maskSensitive((row as Record<string, unknown>).input) }}</template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="100" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click.stop="showDetail(row.log_id)">{{ t('monitoring.requestDetail') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination :total="details?.total || 0" :page-size="page.limit" :current-page="Math.floor(page.offset / page.limit) + 1" layout="prev, pager, next" @current-change="onPageChange" />
    </el-card>
    <el-dialog v-model="detailVisible" :title="t('monitoring.requestDetail')" width="60%">
      <pre class="json-detail">{{ JSON.stringify(detailRow, null, 2) }}</pre>
    </el-dialog>
  </div>
</template>

<style scoped>
.monitoring-page { display: flex; flex-direction: column; gap: 12px; }
.toolbar { display: flex; gap: 8px; align-items: center; }
.json-detail {
  margin: 0;
  padding: var(--spacing-md);
  max-height: 60vh;
  overflow: auto;
  background: var(--bg-page);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  font-family: 'Geist Mono', 'Cascadia Code', Consolas, monospace;
  font-size: var(--font-size-small);
  line-height: var(--line-height-relaxed);
  color: var(--text-regular);
}
</style>

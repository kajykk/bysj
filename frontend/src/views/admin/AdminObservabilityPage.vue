<!-- frontend/src/views/admin/AdminObservabilityPage.vue -->
<script setup lang="ts">
import { ref, onMounted, onUnmounted, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { observabilityApi, type ObservabilityEnvelope, type ObservabilityTimeRange } from '@/api/observabilityApi'
import { showHttpFeedback } from '@/utils/httpFeedback'

const { t } = useI18n()
const MAX_RANGE_DAYS = 30

interface BlockState<T> { loading: boolean; data: ObservabilityEnvelope<T> | null; error: string | null; cached: boolean }

function makeBlock<T>(): BlockState<T> {
  return reactive({ loading: false, data: null, error: null, cached: false })
}

const range = reactive<ObservabilityTimeRange>({ start_time: undefined, end_time: undefined })
const health = makeBlock<{ status: string }>()
const trend = makeBlock<{ points: unknown[] }>()
const responseTime = makeBlock<{ avg_ms: number }>()
const escalation = makeBlock<{ escalation_rate: number }>()
const channelStats = makeBlock<{ channels: unknown[] }>()
const silenceHit = makeBlock<{ hit_rate: number }>()
const amSync = makeBlock<{ last_sync: string }>()
const lockStats = makeBlock<{ active_locks: number }>()

const autoRefresh = ref(false)
const refreshTimer = ref<ReturnType<typeof setInterval> | null>(null)

function defaultRange(): ObservabilityTimeRange {
  const end = new Date()
  const start = new Date(end.getTime() - 24 * 3600 * 1000)
  return { start_time: start.toISOString().slice(0, 10), end_time: end.toISOString().slice(0, 10) }
}

async function loadBlock<T>(block: BlockState<T>, fn: (q?: ObservabilityTimeRange) => Promise<ObservabilityEnvelope<T>>) {
  block.loading = true
  block.error = null
  try {
    const env = await fn(range.start_time && range.end_time ? range : undefined)
    block.data = env
    block.cached = env.cached
  } catch (e) {
    block.error = e instanceof Error ? e.message : 'error'
  } finally {
    block.loading = false
  }
}

async function loadAll() {
  await Promise.allSettled([
    loadBlock(health, observabilityApi.getHealth),
    loadBlock(trend, observabilityApi.getTrend),
    loadBlock(responseTime, observabilityApi.getResponseTime),
    loadBlock(escalation, observabilityApi.getEscalation),
    loadBlock(channelStats, observabilityApi.getChannelStats),
    loadBlock(silenceHit, observabilityApi.getSilenceHitRate),
    loadBlock(amSync, observabilityApi.getAmSync),
    loadBlock(lockStats, observabilityApi.getLockStats),
  ])
}

function toggleAutoRefresh(val: boolean) {
  if (val) {
    refreshTimer.value = setInterval(loadAll, 60000)
  } else if (refreshTimer.value) {
    clearInterval(refreshTimer.value)
    refreshTimer.value = null
  }
}

onMounted(() => { Object.assign(range, defaultRange()); loadAll() })
onUnmounted(() => { if (refreshTimer.value) clearInterval(refreshTimer.value) })
</script>

<template>
  <div class="observability-page">
    <div class="toolbar">
      <el-date-picker v-model="range.start_time" type="date" placeholder="start" />
      <el-date-picker v-model="range.end_time" type="date" placeholder="end" />
      <el-button @click="loadAll">{{ t('common.refresh') }}</el-button>
      <el-switch v-model="autoRefresh" @change="toggleAutoRefresh" :active-text="t('common.autoRefresh')" />
    </div>
    <el-row :gutter="12">
      <el-col :span="6">
        <el-card v-loading="health.loading">
          <template #header>{{ t('observability.health') }}<el-tag v-if="health.cached" size="small">cached</el-tag></template>
          <div v-if="health.error" class="err">{{ health.error }}</div>
          <div v-else>{{ health.data?.data?.status }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-loading="responseTime.loading">
          <template #header>{{ t('observability.responseTime') }}</template>
          <div v-if="responseTime.error" class="err">{{ responseTime.error }}</div>
          <div v-else>{{ responseTime.data?.data?.avg_ms }} ms</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-loading="escalation.loading">
          <template #header>{{ t('observability.escalation') }}</template>
          <div v-if="escalation.error" class="err">{{ escalation.error }}</div>
          <div v-else>{{ escalation.data?.data?.escalation_rate }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-loading="silenceHit.loading">
          <template #header>{{ t('observability.silenceHitRate') }}</template>
          <div v-if="silenceHit.error" class="err">{{ silenceHit.error }}</div>
          <div v-else>{{ silenceHit.data?.data?.hit_rate }}</div>
        </el-card>
      </el-col>
    </el-row>
    <el-row :gutter="12" style="margin-top: 12px">
      <el-col :span="12">
        <el-card v-loading="trend.loading">
          <template #header>{{ t('observability.trend') }}</template>
          <div v-if="trend.error" class="err">{{ trend.error }}</div>
          <div v-else>{{ trend.data?.data?.points?.length }} points</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-loading="amSync.loading">
          <template #header>{{ t('observability.amSync') }}</template>
          <div v-if="amSync.error" class="err">{{ amSync.error }}</div>
          <div v-else>{{ amSync.data?.data?.last_sync }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card v-loading="lockStats.loading">
          <template #header>{{ t('observability.lockStats') }}</template>
          <div v-if="lockStats.error" class="err">{{ lockStats.error }}</div>
          <div v-else>{{ lockStats.data?.data?.active_locks }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.observability-page { display: flex; flex-direction: column; gap: 12px; }
.toolbar { display: flex; gap: 8px; align-items: center; }
.err { color: var(--el-color-danger); }
</style>

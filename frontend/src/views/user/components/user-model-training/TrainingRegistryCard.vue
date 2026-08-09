<template>
  <el-card
    v-if="canTrain"
    shadow="never"
    class="action-card registry-card section-card"
  >
    <template #header>
      <div class="header-row">
        <span class="card-title">{{ t('userModelTraining.registryTitle') }}</span>
        <div class="header-status">
          <el-tag
            type="info"
            effect="plain"
          >
            {{ t('userModelTraining.registryScope') }}
          </el-tag>
          <el-button
            size="small"
            :loading="loading"
            @click="refresh"
          >
            {{ t('userModelTraining.refreshBtn') }}
          </el-button>
          <el-button
            size="small"
            type="warning"
            plain
            :loading="checkingRollback"
            @click="runAutoRollbackCheck"
          >
            {{ t('userModelTraining.registryRunRollbackCheck') }}
          </el-button>
        </div>
      </div>
    </template>

    <el-empty
      v-if="!loading && records.length === 0"
      :description="t('userModelTraining.registryEmpty')"
      :image-size="72"
      class="registry-empty"
    />

    <el-table
      v-else
      v-loading="loading"
      :data="records"
      size="small"
      class="registry-table"
    >
      <el-table-column
        :label="t('userModelTraining.registryColModel')"
        min-width="160"
      >
        <template #default="scope">
          <div
            v-if="scope && scope.row"
            class="model-cell"
          >
            <span class="model-id">{{ scope.row.model_id }}</span>
            <span class="model-version">{{ scope.row.version }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column
        :label="t('userModelTraining.registryColStatus')"
        width="110"
      >
        <template #default="scope">
          <el-tag
            v-if="scope && scope.row"
            :type="statusTagType(scope.row.status)"
            :effect="scope.row.status === 'production' ? 'dark' : 'light'"
          >
            {{ statusLabel(scope.row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column
        :label="t('userModelTraining.registryColMetrics')"
        min-width="180"
      >
        <template #default="scope">
          <div
            v-if="scope && scope.row"
            class="metrics-text"
          >
            {{ metricsSummary(scope.row) }}
          </div>
        </template>
      </el-table-column>

      <el-table-column
        :label="t('userModelTraining.registryColShadow')"
        min-width="150"
      >
        <template #default="scope">
          <template v-if="scope && scope.row">
            <div v-if="shadowTotal(scope.row) > 0">
              <div>{{ t('userModelTraining.registryShadowSamples', { total: shadowTotal(scope.row) }) }}</div>
              <div
                class="shadow-rate"
                :class="{ 'shadow-ok': shadowRate(scope.row) >= 0.75, 'shadow-bad': shadowRate(scope.row) < 0.75 }"
              >
                {{ shadowRateText(scope.row) }}
              </div>
            </div>
            <span
              v-else
              class="muted-text"
            >
              {{ t('userModelTraining.registryShadowNone') }}
            </span>
          </template>
        </template>
      </el-table-column>

      <el-table-column
        :label="t('userModelTraining.registryColArtifact')"
        min-width="200"
      >
        <template #default="scope">
          <el-tooltip
            v-if="scope && scope.row"
            :content="scope.row.artifact_path"
            placement="top-start"
            :show-after="300"
          >
            <span class="artifact-path">{{ scope.row.artifact_path }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column
        :label="t('userModelTraining.registryColUpdated')"
        width="150"
      >
        <template #default="scope">
          <span
            v-if="scope && scope.row"
            class="muted-text"
          >{{ formatTime(scope.row.updated_at) }}</span>
        </template>
      </el-table-column>

      <el-table-column
        :label="t('userModelTraining.registryColActions')"
        width="110"
        align="center"
      >
        <template #default="scope">
          <template v-if="scope && scope.row">
            <el-button
              v-if="scope.row.status === 'production'"
              size="small"
              type="danger"
              plain
              :loading="actionModelId === scope.row.model_id"
              @click="confirmRollback(scope.row)"
            >
              {{ t('userModelTraining.registryRollback') }}
            </el-button>
            <el-button
              v-else-if="scope.row.status === 'candidate' || scope.row.status === 'staging'"
              size="small"
              type="success"
              plain
              :loading="actionModelId === scope.row.model_id"
              @click="confirmActivate(scope.row)"
            >
              {{ t('userModelTraining.registryActivate') }}
            </el-button>
            <span
              v-else
              class="muted-text"
            >
              —
            </span>
          </template>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { modelApi, type ModelRegistryRecord } from '@/api/modelApi'

defineProps<{
  canTrain: boolean
}>()

const { t } = useI18n()

const records = ref<ModelRegistryRecord[]>([])
const loading = ref(false)
const checkingRollback = ref(false)
const actionModelId = ref('')

const METRIC_KEYS = ['accuracy', 'f1', 'precision', 'recall', 'auc'] as const

const statusTagType = (status: ModelRegistryRecord['status']): 'success' | 'warning' | 'info' => {
  if (status === 'production') return 'success'
  if (status === 'staging') return 'warning'
  return 'info'
}

const STATUS_KEYS: Record<ModelRegistryRecord['status'], string> = {
  candidate: 'userModelTraining.registryStatusCandidate',
  staging: 'userModelTraining.registryStatusStaging',
  production: 'userModelTraining.registryStatusProduction',
  retired: 'userModelTraining.registryStatusRetired',
}

const statusLabel = (status: ModelRegistryRecord['status']): string => t(STATUS_KEYS[status] as never)

const metricsSummary = (row: ModelRegistryRecord): string => {
  const parts = METRIC_KEYS
    .filter(key => row.metrics[key] !== undefined)
    .map(key => `${key}=${Number(row.metrics[key]).toFixed(4)}`)
  return parts.length > 0 ? parts.join('  ') : t('userModelTraining.registryNoMetrics')
}

const shadowTotal = (row: ModelRegistryRecord): number => {
  const value = row.metrics.shadow_total
  return value != null && Number.isFinite(value) ? Number(value) : 0
}

const shadowRate = (row: ModelRegistryRecord): number => {
  const value = row.metrics.shadow_agreement_rate
  return value != null && Number.isFinite(value) ? Number(value) : 0
}

const shadowRateText = (row: ModelRegistryRecord): string =>
  `${(shadowRate(row) * 100).toFixed(1)}%`

const formatTime = (iso: string): string => {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

const refresh = async (): Promise<void> => {
  loading.value = true
  try {
    records.value = await modelApi.getModelRegistry()
  } catch {
    records.value = []
    ElMessage.warning(t('userModelTraining.registryLoadFailed'))
  } finally {
    loading.value = false
  }
}

const confirmActivate = async (row: ModelRegistryRecord): Promise<void> => {
  try {
    await ElMessageBox.confirm(
      t('userModelTraining.registryActivateConfirm', { modelId: row.model_id }),
      t('userModelTraining.registryActivate'),
      { type: 'warning', confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel') },
    )
  } catch {
    return
  }
  actionModelId.value = row.model_id
  try {
    await modelApi.activateRegistryModel(row.model_id)
    ElMessage.success(t('userModelTraining.registryActivated', { modelId: row.model_id }))
    await refresh()
  } catch {
    // 影子对拍未达标等错误已由请求层统一提示
  } finally {
    actionModelId.value = ''
  }
}

const confirmRollback = async (row: ModelRegistryRecord): Promise<void> => {
  try {
    await ElMessageBox.confirm(
      t('userModelTraining.registryRollbackConfirm', { modelId: row.model_id }),
      t('userModelTraining.registryRollback'),
      { type: 'warning', confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel') },
    )
  } catch {
    return
  }
  actionModelId.value = row.model_id
  try {
    await modelApi.rollbackRegistryModel(row.model_id)
    ElMessage.success(t('userModelTraining.registryRolledBack', { modelId: row.model_id }))
    await refresh()
  } catch {
    // 错误已由请求层统一提示
  } finally {
    actionModelId.value = ''
  }
}

const runAutoRollbackCheck = async (): Promise<void> => {
  checkingRollback.value = true
  try {
    const result = await modelApi.runAutoRollbackCheck()
    const rolledBack = result.results.filter(item => item.rolled_back).length
    if (rolledBack > 0) {
      ElMessage.success(t('userModelTraining.registryCheckRolledBack', { count: rolledBack }))
    } else {
      ElMessage.info(t('userModelTraining.registryCheckNoRollback'))
    }
    await refresh()
  } catch {
    // 错误已由请求层统一提示
  } finally {
    checkingRollback.value = false
  }
}

onMounted(() => {
  void refresh()
})
</script>

<style scoped>
.registry-card {
  min-height: 260px;
  border-radius: 16px;
}

.section-card {
  margin-top: var(--spacing-lg);
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
  align-items: center;
}

.card-title {
  font-weight: var(--font-weight-bold);
}

.registry-empty {
  padding: 24px 0;
}

.model-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.model-id {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.model-version {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.metrics-text {
  font-family: var(--font-mono, monospace);
  font-size: var(--font-size-extra-small);
  color: var(--text-regular);
  white-space: pre-line;
  line-height: 1.5;
}

.shadow-rate {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-extra-small);
}

.shadow-ok {
  color: var(--success-color, #67c23a);
}

.shadow-bad {
  color: var(--danger-color, #f56c6c);
}

.artifact-path {
  font-family: var(--font-mono, monospace);
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.muted-text {
  color: var(--text-secondary);
  font-size: var(--font-size-extra-small);
}
</style>

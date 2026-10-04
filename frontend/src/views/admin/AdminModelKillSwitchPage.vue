<template>
  <div class="kill-switch-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">{{ t('adminKillSwitch.title') }}</span>
          <el-tag
            :type="paused ? 'danger' : 'success'"
            effect="dark"
          >
            {{ paused ? t('adminKillSwitch.statePaused') : t('adminKillSwitch.stateRunning') }}
          </el-tag>
        </div>
      </template>

      <!-- AUDIT-2026-10-01 (P1-7)：degraded 必须显式呈现，不能只显示「未暂停」 -->
      <el-alert
        v-if="status && status.degraded"
        :type="sourceUnavailable ? 'error' : 'warning'"
        :title="degradedTitle"
        show-icon
        :closable="false"
        class="degraded-alert"
      >
        <template #default>
          <span class="degraded-desc">{{ degradedDesc }}</span>
        </template>
      </el-alert>

      <el-descriptions
        :column="2"
        border
        size="small"
      >
        <el-descriptions-item :label="t('adminKillSwitch.reason')">
          {{ status?.reason || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminKillSwitch.activatedBy')">
          {{ status?.activated_by ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminKillSwitch.activatedAt')">
          {{ formatTime(status?.activated_at) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminKillSwitch.updatedAt')">
          {{ formatTime(status?.updated_at) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminKillSwitch.source')">
          {{ sourceLabel }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="action-area">
        <el-form label-position="top">
          <el-form-item :label="t('adminKillSwitch.reasonInput')">
            <el-input
              v-model="reason"
              type="textarea"
              :rows="3"
              maxlength="500"
              show-word-limit
              :placeholder="t('adminKillSwitch.reasonPlaceholder')"
            />
          </el-form-item>
          <el-form-item>
            <el-button
              v-if="!paused"
              type="danger"
              :loading="submitting"
              :disabled="!reason.trim()"
              @click="handleActivate"
            >
              {{ t('adminKillSwitch.btnPause') }}
            </el-button>
            <el-button
              v-else
              type="success"
              :loading="submitting"
              :disabled="!reason.trim()"
              @click="handleDeactivate"
            >
              {{ t('adminKillSwitch.btnResume') }}
            </el-button>
            <el-button
              :loading="loading"
              @click="loadStatus"
            >
              {{ t('adminKillSwitch.btnRefresh') }}
            </el-button>
          </el-form-item>
        </el-form>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { killSwitchApi, type KillSwitchState } from '@/api/killSwitchApi'
import { formatDate } from '@/utils/formatUtils'
import { normalizeHttpError } from '@/utils/errorPolicy'

defineOptions({ name: 'AdminModelKillSwitchPage' })

const { t } = useI18n()

const status = ref<KillSwitchState | null>(null)
const loading = ref(false)
const submitting = ref(false)
const reason = ref('')

const paused = computed(() => status.value?.paused ?? false)
const sourceUnavailable = computed(() => status.value?.source === 'unavailable')

const degradedTitle = computed(() =>
  sourceUnavailable.value
    ? t('adminKillSwitch.degradedUnavailableTitle')
    : t('adminKillSwitch.degradedMemoryTitle')
)
const degradedDesc = computed(() =>
  sourceUnavailable.value
    ? t('adminKillSwitch.degradedUnavailableDesc')
    : t('adminKillSwitch.degradedMemoryDesc')
)
const sourceLabel = computed(() => {
  const src = status.value?.source
  if (src === 'redis') return t('adminKillSwitch.sourceRedis')
  if (src === 'memory') return t('adminKillSwitch.sourceMemory')
  if (src === 'unavailable') return t('adminKillSwitch.sourceUnavailable')
  return '-'
})

const formatTime = (value: string | null | undefined) => (value ? formatDate(value) : '-')

const loadStatus = async () => {
  loading.value = true
  try {
    status.value = await killSwitchApi.getStatus()
  } catch (error) {
    // 加载失败时不清空 status（保留上一次已知状态），但置空以便 degraded 得到呈现
    status.value = null
    ElMessage.error(normalizeHttpError(error, t('adminKillSwitch.loadFailed')).detail)
  } finally {
    loading.value = false
  }
}

const confirmThen = async (titleKey: string, textKey: string) => {
  try {
    await ElMessageBox.confirm(t(textKey), t(titleKey), {
      type: 'warning',
      confirmButtonText: t('adminKillSwitch.confirmBtn'),
      cancelButtonText: t('adminKillSwitch.cancelBtn'),
    })
    return true
  } catch {
    return false
  }
}

const handleActivate = async () => {
  if (!(await confirmThen('adminKillSwitch.pauseConfirmTitle', 'adminKillSwitch.pauseConfirmText'))) {
    return
  }
  await submit(() => killSwitchApi.activate(reason.value.trim()), 'adminKillSwitch.pauseSuccess')
}

const handleDeactivate = async () => {
  if (!(await confirmThen('adminKillSwitch.resumeConfirmTitle', 'adminKillSwitch.resumeConfirmText'))) {
    return
  }
  await submit(() => killSwitchApi.deactivate(reason.value.trim()), 'adminKillSwitch.resumeSuccess')
}

const submit = async (action: () => Promise<KillSwitchState>, successKey: string) => {
  submitting.value = true
  try {
    status.value = await action()
    reason.value = ''
    ElMessage.success(t(successKey))
  } catch (error) {
    // fail-closed 下后端返回 503 表示**操作未生效**，必须原样呈现，不能吞成「成功」
    ElMessage.error(normalizeHttpError(error, t('adminKillSwitch.actionFailed')).detail)
    // 操作失败后刷新一次，避免界面停留在旧状态
    await loadStatus()
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadStatus()
})
</script>

<style scoped>
.kill-switch-page {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: var(--font-size-medium);
  font-weight: 600;
}

.degraded-alert {
  margin-bottom: var(--spacing-md);
}

.degraded-desc {
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}

.action-area {
  margin-top: var(--spacing-lg);
}
</style>

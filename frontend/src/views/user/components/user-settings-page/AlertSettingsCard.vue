<template>
  <el-card>
    <template #header>
      <span class="card-title">{{ t('userSettings.alert.title') }}</span>
    </template>
    <div
      v-if="settingsLoading"
      class="skeleton-padding"
    >
      <el-skeleton
        :rows="4"
        animated
      />
    </div>
    <el-form
      v-else
      :model="settingsForm"
      label-width="120px"
    >
      <el-form-item :label="t('userSettings.alert.channels')">
        <el-checkbox-group v-model="settingsForm.notify_channels">
          <el-checkbox
            :label="t('userSettings.alert.channelInApp')"
            value="in_app"
          />
          <el-checkbox
            :label="t('userSettings.alert.channelEmail')"
            value="email"
          />
          <el-checkbox
            :label="t('userSettings.alert.channelSms')"
            value="sms"
          />
        </el-checkbox-group>
      </el-form-item>
      <el-form-item :label="t('userSettings.alert.thresholdLevel')">
        <el-select
          v-model="settingsForm.threshold_level"
          style="width: 200px"
        >
          <el-option
            :label="t('userSettings.alert.level1')"
            :value="1"
          />
          <el-option
            :label="t('userSettings.alert.level2')"
            :value="2"
          />
          <el-option
            :label="t('userSettings.alert.level3')"
            :value="3"
          />
          <el-option
            :label="t('userSettings.alert.level4')"
            :value="4"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('userSettings.alert.quietHours')">
        <div class="quiet-hours-row">
          <el-time-select
            v-model="settingsForm.quiet_hours_start"
            :max-time="settingsForm.quiet_hours_end"
            :placeholder="t('userSettings.alert.start')"
            start="00:00"
            step="00:30"
            end="23:30"
          />
          <span>{{ t('userSettings.alert.to') }}</span>
          <el-time-select
            v-model="settingsForm.quiet_hours_end"
            :min-time="settingsForm.quiet_hours_start"
            :placeholder="t('userSettings.alert.end')"
            start="00:00"
            step="00:30"
            end="23:30"
          />
        </div>
      </el-form-item>
      <el-form-item>
        <el-button
          type="primary"
          :loading="settingsSaving"
          @click="saveSettings"
        >
          {{ t('userSettings.alert.save') }}
        </el-button>
        <el-button
          class="reset-btn"
          @click="resetSettingsForm"
        >
          {{ t('userSettings.alert.reset') }}
        </el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'AlertSettingsCard' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { userApi } from '@/api/userApi'
import { normalizeHttpError } from '@/utils/errorPolicy'

const { t } = useI18n()

const settingsLoading = ref(true)
const settingsSaving = ref(false)
const settingsForm = reactive({
  notify_channels: ['in_app'] as string[],
  threshold_level: 2,
  quiet_hours_start: '' as string | null,
  quiet_hours_end: '' as string | null
})

const channelKeys = ['in_app', 'email', 'sms', 'websocket'] as const

const channelsToRecord = (channels: string[]): Record<string, boolean> => {
  const result: Record<string, boolean> = { in_app: false, email: false, sms: false, websocket: false }
  for (const key of channelKeys) {
    result[key] = channels.includes(key)
  }
  return result
}

const recordToChannels = (record: Record<string, boolean> | null | undefined): string[] => {
  if (!record) return ['in_app']
  return channelKeys.filter((key) => Boolean(record[key]))
}

const loadSettings = async () => {
  settingsLoading.value = true
  try {
    const data = await userApi.getWarningSettings()
    settingsForm.notify_channels = recordToChannels(data.notify_channels)
    settingsForm.threshold_level = data.threshold_level || 2
    settingsForm.quiet_hours_start = data.quiet_hours_start || ''
    settingsForm.quiet_hours_end = data.quiet_hours_end || ''
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userSettings.alert.loadFailed')).detail)
  } finally {
    settingsLoading.value = false
  }
}

const saveSettings = async () => {
  settingsSaving.value = true
  try {
    await userApi.updateWarningSettings({
      notify_channels: channelsToRecord(settingsForm.notify_channels),
      threshold_level: settingsForm.threshold_level,
      quiet_hours_start: settingsForm.quiet_hours_start || undefined,
      quiet_hours_end: settingsForm.quiet_hours_end || undefined
    })
    ElMessage.success(t('userSettings.alert.saved'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userSettings.alert.saveFailed')).detail)
  } finally {
    settingsSaving.value = false
  }
}

const resetSettingsForm = () => {
  settingsForm.notify_channels = ['in_app']
  settingsForm.threshold_level = 2
  settingsForm.quiet_hours_start = ''
  settingsForm.quiet_hours_end = ''
}

onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.skeleton-padding {
  padding: var(--spacing-xl);
}

.quiet-hours-row {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
}

.reset-btn {
  margin-left: var(--spacing-sm);
}

@media (max-width: 768px) {
  .quiet-hours-row {
    flex-direction: column;
    align-items: stretch;
    gap: var(--spacing-xs);
  }
}
</style>

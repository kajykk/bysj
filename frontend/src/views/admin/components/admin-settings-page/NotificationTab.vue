<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span class="card-title">{{ t('adminSettings.notification.cardTitle') }}</span>
        <el-button
          type="primary"
          size="small"
          :loading="notificationSaving"
          @click="saveNotificationConfig"
        >
          {{ t('common.save') }}
        </el-button>
      </div>
    </template>
    <el-form
      :model="notificationForm"
      label-width="160px"
      class="notification-form"
    >
      <el-form-item :label="t('adminSettings.notification.email')">
        <el-switch v-model="notificationForm.notification_email_enabled" />
        <span class="form-hint">{{ t('adminSettings.notification.emailHint') }}</span>
      </el-form-item>
      <el-form-item :label="t('adminSettings.notification.sms')">
        <el-switch v-model="notificationForm.notification_sms_enabled" />
        <span class="form-hint">{{ t('adminSettings.notification.smsHint') }}</span>
      </el-form-item>
      <el-form-item :label="t('adminSettings.notification.webhookUrl')">
        <el-input
          v-model="notificationForm.notification_webhook_url"
          placeholder="https://example.com/webhook"
          style="max-width: 420px"
        />
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'NotificationTab' })
import { reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { adminApi, type ConfigItem } from '@/api/adminApi'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { getConfigValue } from './adminSettingsUtils'

const props = defineProps<{
  configs: ConfigItem[]
}>()

const emit = defineEmits<{ reload: [] }>()

const { t } = useI18n()

// ISS-077: 通知配置
const notificationForm = reactive({
  notification_email_enabled: false,
  notification_sms_enabled: false,
  notification_webhook_url: '',
})
const notificationSaving = ref(false)

const loadNotificationConfig = () => {
  notificationForm.notification_email_enabled = getConfigValue(props.configs, 'notification_email_enabled', false)
  notificationForm.notification_sms_enabled = getConfigValue(props.configs, 'notification_sms_enabled', false)
  notificationForm.notification_webhook_url = getConfigValue(props.configs, 'notification_webhook_url', '')
}

const saveNotificationConfig = async () => {
  notificationSaving.value = true
  try {
    await Promise.all([
      adminApi.upsertAdminConfig({ config_key: 'notification_email_enabled', config_value: { value: notificationForm.notification_email_enabled } }),
      adminApi.upsertAdminConfig({ config_key: 'notification_sms_enabled', config_value: { value: notificationForm.notification_sms_enabled } }),
      adminApi.upsertAdminConfig({ config_key: 'notification_webhook_url', config_value: { value: notificationForm.notification_webhook_url } }),
    ])
    ElMessage.success(t('adminSettings.notification.saved'))
    emit('reload')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('adminSettings.notification.saveFailed')).detail)
  } finally {
    notificationSaving.value = false
  }
}

// configs 由父组件加载，加载完成后同步表单值
watch(() => props.configs, () => {
  loadNotificationConfig()
}, { immediate: true, deep: true })
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* ISS-077: 通知配置表单提示 */
.form-hint {
  margin-left: 12px;
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.notification-form {
  max-width: 640px;
}
</style>

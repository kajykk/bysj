<template>
  <div class="settings-page">
    <el-row :gutter="16">
      <el-col
        :xs="24"
        :md="12"
      >
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
      </el-col>

      <el-col
        :xs="24"
        :md="12"
      >
        <el-card v-if="auth.role === 'user'">
          <template #header>
            <span class="card-title">{{ t('userSettings.binding.title') }}</span>
          </template>
          <div
            v-if="bindingLoading"
            class="skeleton-padding"
          >
            <el-skeleton
              :rows="3"
              animated
            />
          </div>
          <template v-else-if="currentBinding">
            <el-descriptions
              :column="1"
              border
            >
              <el-descriptions-item :label="t('userSettings.binding.counselor')">
                {{ currentBinding.counselor_name }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('userSettings.binding.bindTime')">
                {{ formatDate(currentBinding.bound_at) }}
              </el-descriptions-item>
            </el-descriptions>
            <div class="unbind-row">
              <el-button
                type="danger"
                plain
                :loading="unbindLoading"
                @click="handleUnbind"
              >
                {{ t('userSettings.binding.unbind') }}
              </el-button>
            </div>
          </template>
          <template v-else>
            <el-form
              :model="bindForm"
              label-width="100px"
              @submit.prevent="handleBind"
            >
              <el-form-item
                :label="t('userSettings.binding.bindCode')"
                required
              >
                <el-input
                  v-model="bindForm.bind_code"
                  :placeholder="t('userSettings.binding.bindCodePlaceholder')"
                  :maxlength="10"
                  clearable
                />
              </el-form-item>
              <el-form-item>
                <el-button
                  type="primary"
                  :loading="bindLoading"
                  @click="handleBind"
                >
                  {{ t('userSettings.binding.bind') }}
                </el-button>
              </el-form-item>
            </el-form>
            <div class="bind-tip">
              <el-icon><InfoFilled /></el-icon>
              <span>{{ t('userSettings.binding.tip') }}</span>
            </div>
          </template>
        </el-card>

        <el-card class="section-card">
          <template #header>
            <span class="card-title">{{ t('userSettings.profile.title') }}</span>
          </template>
          <el-form
            :model="profileForm"
            label-width="100px"
          >
            <el-form-item :label="t('userSettings.profile.username')">
              <el-input
                :model-value="auth.user?.username"
                disabled
              />
            </el-form-item>
            <el-form-item :label="t('userSettings.profile.role')">
              <el-input
                :model-value="roleLabel"
                disabled
              />
            </el-form-item>
            <el-form-item :label="t('userSettings.profile.nickname')">
              <el-input
                v-model="profileForm.nickname"
                :placeholder="t('userSettings.profile.nicknamePlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('userSettings.profile.email')">
              <el-input
                v-model="profileForm.email"
                :placeholder="t('userSettings.profile.emailPlaceholder')"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="profileSaving"
                @click="saveProfile"
              >
                {{ t('userSettings.profile.save') }}
              </el-button>
              <el-button
                class="reset-btn"
                @click="resetProfileForm"
              >
                {{ t('userSettings.profile.reset') }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="section-card">
          <template #header>
            <span class="card-title">{{ t('userSettings.password.title') }}</span>
          </template>
          <el-form
            :model="passwordForm"
            label-width="100px"
          >
            <el-form-item
              :label="t('userSettings.password.current')"
              required
            >
              <el-input
                v-model="passwordForm.old_password"
                type="password"
                show-password
              />
            </el-form-item>
            <el-form-item
              :label="t('userSettings.password.new')"
              required
            >
              <el-input
                v-model="passwordForm.new_password"
                type="password"
                show-password
              />
            </el-form-item>
            <el-form-item
              :label="t('userSettings.password.confirm')"
              required
            >
              <el-input
                v-model="passwordForm.confirm_password"
                type="password"
                show-password
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="passwordSaving"
                @click="changePassword"
              >
                {{ t('userSettings.password.submit') }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="section-card">
          <template #header>
            <span class="card-title">{{ t('userSettings.gdpr.title') }}</span>
          </template>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="gdpr-alert"
          >
            <template #default>
              {{ t('userSettings.gdpr.description') }}
            </template>
          </el-alert>

          <div class="gdpr-actions">
            <div class="gdpr-action-row">
              <div class="gdpr-action-info">
                <div class="gdpr-action-title">
                  {{ t('userSettings.gdpr.exportTitle') }}
                </div>
                <div class="gdpr-action-desc">
                  {{ t('userSettings.gdpr.exportDesc') }}
                </div>
              </div>
              <el-button
                type="primary"
                plain
                :loading="exportLoading"
                @click="handleExportData"
              >
                {{ t('userSettings.gdpr.exportBtn') }}
              </el-button>
            </div>

            <el-divider />

            <div class="gdpr-action-row">
              <div class="gdpr-action-info">
                <div class="gdpr-action-title gdpr-danger-title">
                  {{ t('userSettings.gdpr.anonymizeTitle') }}
                </div>
                <div class="gdpr-action-desc">
                  {{ t('userSettings.gdpr.anonymizeDesc') }}
                </div>
              </div>
              <el-button
                type="danger"
                @click="openDeleteDialog"
              >
                {{ t('userSettings.gdpr.deleteBtn') }}
              </el-button>
            </div>
          </div>
        </el-card>

        <!-- P1-5 埋点与隐私闭环：分析同意管理 -->
        <el-card class="section-card">
          <template #header>
            <span class="card-title">{{ t('userSettings.analytics.title') }}</span>
          </template>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="gdpr-alert"
          >
            <template #default>
              {{ t('userSettings.analytics.description') }}
            </template>
          </el-alert>
          <div class="analytics-consent-row">
            <div class="analytics-consent-info">
              <div class="analytics-consent-label">
                {{ t('userSettings.analytics.consentLabel') }}
              </div>
              <div class="analytics-consent-desc">
                {{ t('userSettings.analytics.consentDesc') }}
              </div>
              <div class="analytics-consent-meta">
                <span class="analytics-meta-item">
                  <strong>{{ t('userSettings.analytics.retentionLabel') }}:</strong>
                  {{ t('userSettings.analytics.retentionValue') }}
                </span>
              </div>
              <div class="analytics-consent-meta">
                <span class="analytics-meta-item">
                  <strong>{{ t('userSettings.analytics.eventTypesLabel') }}:</strong>
                  {{ t('userSettings.analytics.eventTypes') }}
                </span>
              </div>
              <div class="analytics-consent-note">
                {{ t('userSettings.analytics.privacyNote') }}
              </div>
            </div>
            <el-switch
              :model-value="consented"
              :loading="analyticsConsentSaving"
              @change="handleAnalyticsConsentChange"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog
      v-model="deleteDialogVisible"
      :title="t('userSettings.gdpr.deleteDialogTitle')"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-alert
        type="error"
        :closable="false"
        show-icon
        class="gdpr-alert"
      >
        {{ t('userSettings.gdpr.deleteDialogAlert') }}
      </el-alert>
      <el-form
        class="gdpr-delete-form"
        label-width="100px"
      >
        <el-form-item
          :label="t('userSettings.gdpr.deleteCurrentPassword')"
          required
        >
          <el-input
            v-model="deleteForm.password"
            type="password"
            show-password
            :placeholder="t('userSettings.gdpr.deleteCurrentPasswordPlaceholder')"
          />
        </el-form-item>
        <el-form-item
          :label="t('userSettings.gdpr.deleteConfirmLabel')"
          required
        >
          <el-input
            v-model="deleteForm.confirmText"
            :placeholder="t('userSettings.gdpr.deleteConfirmPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deleteDialogVisible = false">
          {{ t('userSettings.gdpr.deleteCancel') }}
        </el-button>
        <el-button
          type="danger"
          :loading="deleteLoading"
          :disabled="!canSubmitDelete"
          @click="handleDeleteAccount"
        >
          {{ t('userSettings.gdpr.deleteConfirmBtn') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'UserSettingsPage' })
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import { userApi, type UserBindingInfo } from '@/api/userApi'
import type { BindCounselorResult } from '@/api/userBindingApi'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { setStoredAuth } from '@/utils/authStorage'
import { checkPasswordBytes } from '@/utils/passwordValidation'
// P2-A 修复：复用 formatUtils 的 formatDate，避免本地重复定义
import { formatDate } from '@/utils/formatUtils'
// P1-5 埋点与隐私闭环：分析同意管理
import { useAnalytics } from '@/composables/useAnalytics'

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()

// P1-5 埋点与隐私闭环：分析同意管理
const { consented, refreshConsent, setConsent } = useAnalytics()
const analyticsConsentLoading = ref(false)
const analyticsConsentSaving = ref(false)

const handleAnalyticsConsentChange = async (value: string | number | boolean) => {
  const consent = Boolean(value)
  analyticsConsentSaving.value = true
  try {
    await setConsent(consent)
    ElMessage.success(consent ? t('userSettings.analytics.consentGranted') : t('userSettings.analytics.consentWithdrawn'))
  } catch (error) {
    ElMessage.error(t('userSettings.analytics.updateFailed'))
    // 恢复开关状态
    consented.value = !consent
  } finally {
    analyticsConsentSaving.value = false
  }
}

const roleLabel = computed(() => {
  if (auth.role === 'admin') return t('userSettings.roles.admin')
  if (auth.role === 'counselor') return t('userSettings.roles.counselor')
  return t('userSettings.roles.user')
})

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

const bindingLoading = ref(true)
const currentBinding = ref<UserBindingInfo | null>(null)

const loadBinding = async () => {
  if (auth.role !== 'user') {
    bindingLoading.value = false
    return
  }
  bindingLoading.value = true
  try {
    currentBinding.value = await userApi.getUserBinding()
  } catch (error) {
    currentBinding.value = null
    ElMessage.warning(normalizeHttpError(error, t('userSettings.binding.loadFailed')).detail)
  } finally {
    bindingLoading.value = false
  }
}

const bindForm = reactive({ bind_code: '' })
const bindLoading = ref(false)

const handleBind = async () => {
  if (!bindForm.bind_code.trim()) {
    ElMessage.warning(t('userSettings.binding.bindCodeRequired'))
    return
  }
  bindLoading.value = true
  try {
    const result: BindCounselorResult = await userApi.bindCounselor(bindForm.bind_code.trim())
    currentBinding.value = {
      binding_id: result.binding_id,
      counselor_id: result.counselor_id,
      counselor_name: result.counselor_name,
      counselor_email: result.counselor_email,
      bound_at: result.bound_at,
      status: result.status,
      bind_code_status: result.bind_code_status
    }
    bindForm.bind_code = ''
    ElMessage.success(t('userSettings.binding.bindSuccess', { name: result.counselor_name }))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userSettings.binding.bindFailed')).detail)
  } finally {
    bindLoading.value = false
  }
}

const unbindLoading = ref(false)

// ISS-035 修复：解绑操作销毁绑定关系，确认框类型由 warning 调整为 error
const handleUnbind = async () => {
  try {
    await ElMessageBox.confirm(
      t('userSettings.binding.unbindConfirmContent'),
      t('userSettings.binding.unbindConfirmTitle'),
      { type: 'error' }
    )
  } catch {
    return
  }
  unbindLoading.value = true
  try {
    await userApi.unbindCounselor()
    currentBinding.value = null
    ElMessage.success(t('userSettings.binding.unbindSuccess'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userSettings.binding.unbindFailed')).detail)
  } finally {
    unbindLoading.value = false
  }
}

const profileForm = reactive({
  nickname: auth.user?.nickname || '',
  email: auth.user?.email || ''
})
const profileSaving = ref(false)

const saveProfile = async () => {
  profileSaving.value = true
  try {
    const data = await authApi.updateProfile({
      nickname: profileForm.nickname || undefined,
      email: profileForm.email || undefined
    })
    if (auth.user) {
      auth.user.nickname = data.nickname
      auth.user.email = data.email
      setStoredAuth({ user: auth.user })
    }
    ElMessage.success(t('userSettings.profile.saved'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userSettings.profile.saveFailed')).detail)
  } finally {
    profileSaving.value = false
  }
}

const resetProfileForm = () => {
  profileForm.nickname = auth.user?.nickname || ''
  profileForm.email = auth.user?.email || ''
}

const passwordForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const passwordSaving = ref(false)

const changePassword = async () => {
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    ElMessage.warning(t('userSettings.password.mismatch'))
    return
  }
  if (passwordForm.new_password.length < 8) {
    ElMessage.warning(t('userSettings.password.tooShort'))
    return
  }
  const byteError = checkPasswordBytes(passwordForm.new_password)
  if (byteError) {
    ElMessage.warning(byteError)
    return
  }
  passwordSaving.value = true
  try {
    await authApi.changePassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password
    })
    ElMessage.success(t('userSettings.password.saved'))
    passwordForm.old_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm_password = ''
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userSettings.password.saveFailed')).detail)
  } finally {
    passwordSaving.value = false
  }
}

// ── GDPR：数据导出 & 账户匿名化 ───────────────────────────────────
const exportLoading = ref(false)

const handleExportData = async () => {
  exportLoading.value = true
  try {
    const response = await userApi.exportUserData()
    // 尝试从 Content-Disposition 提取文件名，失败则使用默认名
    const disposition = response.headers['content-disposition'] as string | undefined
    let filename = `my_data_${Date.now()}.json`
    if (disposition) {
      const match = disposition.match(/filename="?([^"]+)"?/)
      if (match && match[1]) filename = match[1]
    }
    const blob = new Blob([response.data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    ElMessage.success(t('userSettings.gdpr.exportSuccess'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userSettings.gdpr.exportFailed')).detail)
  } finally {
    exportLoading.value = false
  }
}

const deleteDialogVisible = ref(false)
const deleteLoading = ref(false)
const deleteForm = reactive({ password: '', confirmText: '' })

const canSubmitDelete = computed(
  () => deleteForm.password.length > 0 && deleteForm.confirmText === t('userSettings.gdpr.deleteKeyword')
)

const openDeleteDialog = () => {
  deleteForm.password = ''
  deleteForm.confirmText = ''
  deleteDialogVisible.value = true
}

const handleDeleteAccount = async () => {
  if (!canSubmitDelete.value) {
    ElMessage.warning(t('userSettings.gdpr.deleteRequireKeywordAndPassword'))
    return
  }
  deleteLoading.value = true
  try {
    await userApi.deleteAccount({ password: deleteForm.password, confirm: true })
    deleteDialogVisible.value = false
    ElMessage.success(t('userSettings.gdpr.anonymized'))
    // 账户已被匿名化 (status=deleted)，后续携带 token 的请求都会 401，
    // 因此直接清理本地认证状态并跳转登录页，不再调用 authApi.logout
    auth.persistAuth({ token: '', refreshToken: '', user: null })
    auth.broadcastAuthSync({ token: '', refreshToken: '', user: null })
    await router.replace('/login')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userSettings.gdpr.deleteFailed')).detail)
  } finally {
    deleteLoading.value = false
  }
}

onMounted(() => {
  loadSettings()
  loadBinding()
  refreshConsent()
})
</script>

<style scoped>
.settings-page {
  padding: 0;
}

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

.unbind-row {
  margin-top: var(--spacing-lg);
}

.section-card {
  margin-top: var(--spacing-lg);
}

.bind-tip {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-xs);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: 1.6;
}

.bind-tip .el-icon {
  margin-top: 3px;
  flex-shrink: 0;
}

.gdpr-alert {
  margin-bottom: var(--spacing-md);
}

.gdpr-actions {
  margin-top: var(--spacing-sm);
}

.gdpr-action-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-md);
}

.gdpr-action-info {
  flex: 1;
  min-width: 0;
}

.gdpr-action-title {
  font-weight: var(--font-weight-semibold);
  margin-bottom: var(--spacing-xs);
}

.gdpr-danger-title {
  color: var(--el-color-danger);
}

.gdpr-action-desc {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: 1.6;
}

.gdpr-delete-form {
  margin-top: var(--spacing-md);
}

/* P1-5 分析同意管理样式 */
.analytics-consent-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-md);
  margin-top: var(--spacing-sm);
}

.analytics-consent-info {
  flex: 1;
  min-width: 0;
}

.analytics-consent-label {
  font-weight: var(--font-weight-semibold);
  margin-bottom: var(--spacing-xs);
}

.analytics-consent-desc {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: 1.6;
  margin-bottom: var(--spacing-sm);
}

.analytics-consent-meta {
  font-size: var(--font-size-small);
  color: var(--text-regular);
  line-height: 1.6;
  margin-bottom: var(--spacing-xs);
}

.analytics-consent-note {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  margin-top: var(--spacing-sm);
}

/* 响应式：移动端适配 */
@media (max-width: 768px) {
  .quiet-hours-row {
    flex-direction: column;
    align-items: stretch;
    gap: var(--spacing-xs);
  }

  .gdpr-action-row {
    flex-direction: column;
    align-items: stretch;
  }

  .gdpr-action-row .el-button {
    width: 100%;
  }
}
</style>

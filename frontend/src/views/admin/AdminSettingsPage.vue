<template>
  <div class="settings-page">
    <el-tabs
      v-model="activeTab"
      type="border-card"
    >
      <el-tab-pane
        :label="t('adminSettings.tabs.thresholds')"
        name="thresholds"
      >
        <el-card>
          <template #header>
            <div class="header-row">
              <span class="card-title">{{ t('adminSettings.thresholds.cardTitle') }}</span>
              <el-button
                type="primary"
                size="small"
                @click="openThresholdCreate"
              >
                {{ t('adminSettings.thresholds.createBtn') }}
              </el-button>
            </div>
          </template>

          <StatefulContainer
            :loading="thresholdLoading"
            :empty="!thresholdLoading && thresholds.length === 0"
            :error-message="thresholdError"
            :empty-text="t('adminSettings.thresholds.empty')"
            @retry="loadThresholds"
          >
            <el-table
              :data="thresholds"
              border
              stripe
            >
              <el-table-column
                prop="level"
                :label="t('adminSettings.thresholds.colLevel')"
                width="80"
              />
              <el-table-column
                prop="level_name"
                :label="t('adminSettings.thresholds.colLevelName')"
                width="120"
              />
              <el-table-column
                prop="min_score"
                :label="t('adminSettings.thresholds.colMinScore')"
                width="100"
              />
              <el-table-column
                prop="max_score"
                :label="t('adminSettings.thresholds.colMaxScore')"
                width="100"
              />
              <el-table-column
                prop="color"
                :label="t('adminSettings.thresholds.colColor')"
                width="100"
              >
                <template #default="{ row }">
                  <span :style="{ color: row.color, fontWeight: 'bold' }">{{ row.color }}</span>
                </template>
              </el-table-column>
              <el-table-column
                prop="action_required"
                :label="t('adminSettings.thresholds.colActionRequired')"
                min-width="200"
              />
              <el-table-column
                :label="t('adminSettings.thresholds.colOperation')"
                width="100"
                fixed="right"
              >
                <template #default="{ row }">
                  <el-button
                    link
                    type="primary"
                    size="small"
                    @click="openThresholdEdit(row)"
                  >
                    {{ t('adminSettings.common.edit') }}
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </StatefulContainer>
        </el-card>
      </el-tab-pane>

      <el-tab-pane
        :label="t('adminSettings.tabs.configs')"
        name="configs"
      >
        <el-card>
          <template #header>
            <div class="header-row">
              <span class="card-title">{{ t('adminSettings.configs.cardTitle') }}</span>
              <el-button
                type="primary"
                size="small"
                @click="openConfigCreate"
              >
                {{ t('adminSettings.configs.createBtn') }}
              </el-button>
            </div>
          </template>

          <StatefulContainer
            :loading="configLoading"
            :empty="!configLoading && configs.length === 0"
            :error-message="configError"
            :empty-text="t('adminSettings.configs.empty')"
            @retry="loadConfigs"
          >
            <el-table
              :data="configs"
              border
              stripe
            >
              <el-table-column
                prop="config_key"
                :label="t('adminSettings.configs.colKey')"
                min-width="180"
              />
              <el-table-column
                prop="config_value"
                :label="t('adminSettings.configs.colValue')"
                min-width="240"
              >
                <template #default="{ row }">
                  <span class="config-value">{{ JSON.stringify(row.config_value) }}</span>
                </template>
              </el-table-column>
              <el-table-column
                prop="description"
                :label="t('adminSettings.configs.colDescription')"
                min-width="180"
              >
                <template #default="{ row }">
                  {{ row.description || '-' }}
                </template>
              </el-table-column>
              <el-table-column
                :label="t('adminSettings.configs.colOperation')"
                width="100"
                fixed="right"
              >
                <template #default="{ row }">
                  <el-button
                    link
                    type="primary"
                    size="small"
                    @click="openConfigEdit(row)"
                  >
                    {{ t('adminSettings.common.edit') }}
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </StatefulContainer>
        </el-card>
      </el-tab-pane>

      <el-tab-pane
        :label="t('adminSettings.tabs.feedbacks')"
        name="feedbacks"
      >
        <el-card>
          <template #header>
            <span class="card-title">{{ t('adminSettings.feedbacks.cardTitle') }}</span>
          </template>
          <StatefulContainer
            :loading="feedbackLoading"
            :empty="!feedbackLoading && feedbacks.length === 0"
            :error-message="feedbackError"
            :empty-text="t('adminSettings.feedbacks.empty')"
            @retry="loadFeedbacks"
          >
            <el-table
              :data="feedbacks"
              border
              stripe
            >
              <el-table-column
                prop="id"
                :label="t('adminSettings.feedbacks.colId')"
                width="80"
              />
              <el-table-column
                prop="counselor_id"
                :label="t('adminSettings.feedbacks.colCounselorId')"
                width="100"
              />
              <el-table-column
                prop="user_id"
                :label="t('adminSettings.feedbacks.colUserId')"
                width="100"
              />
              <el-table-column
                prop="assessment_id"
                :label="t('adminSettings.feedbacks.colAssessmentId')"
                width="100"
              />
              <el-table-column
                prop="agreed"
                :label="t('adminSettings.feedbacks.colAgreed')"
                width="100"
              >
                <template #default="{ row }">
                  <el-tag
                    :type="row.agreed ? 'success' : 'danger'"
                    size="small"
                  >
                    {{ row.agreed ? t('adminSettings.feedbacks.agreed') : t('adminSettings.feedbacks.disagreed') }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                prop="reason"
                :label="t('adminSettings.feedbacks.colReason')"
                min-width="200"
              />
              <el-table-column
                prop="created_at"
                :label="t('adminSettings.feedbacks.colTime')"
                width="180"
              />
            </el-table>
          </StatefulContainer>
          <div class="pager-wrap">
            <el-pagination
              background
              layout="total, prev, pager, next"
              :total="feedbackTotal"
              :page-size="feedbackPageSize"
              :current-page="feedbackPage"
              @current-change="(v: number) => { feedbackPage = v; loadFeedbacks() }"
              @size-change="(v: number) => { feedbackPageSize = v; feedbackPage = 1; loadFeedbacks() }"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <!-- ISS-074: GDPR 合规管理 -->
      <el-tab-pane
        :label="t('adminSettings.tabs.gdpr')"
        name="gdpr"
      >
        <el-card>
          <template #header>
            <div class="header-row">
              <span class="card-title">{{ t('adminSettings.gdpr.cardTitle') }}</span>
              <el-tag
                type="warning"
                size="small"
              >
                {{ t('adminSettings.gdpr.auditTag') }}
              </el-tag>
            </div>
          </template>

          <el-alert
            type="warning"
            :closable="false"
            show-icon
            class="gdpr-alert"
          >
            <template #title>
              {{ t('adminSettings.gdpr.alertTitle') }}
            </template>
            <template #default>
              {{ t('adminSettings.gdpr.alertContent') }}
            </template>
          </el-alert>

          <el-form
            :model="gdprForm"
            label-width="120px"
            class="gdpr-form"
          >
            <el-form-item :label="t('adminSettings.gdpr.targetUserId')">
              <el-input-number
                v-model="gdprForm.userId"
                :min="1"
                :step="1"
                controls-position="right"
                style="width: 200px"
              />
              <el-button
                link
                type="primary"
                :loading="gdprChecking"
                @click="checkUserExists"
              >
                {{ t('adminSettings.gdpr.checkUserBtn') }}
              </el-button>
              <span
                v-if="gdprCheckResult"
                :class="['gdpr-check-result', gdprCheckResult.ok ? 'ok' : 'err']"
              >
                {{ gdprCheckResult.message }}
              </span>
            </el-form-item>
            <el-form-item :label="t('adminSettings.gdpr.reason')">
              <el-input
                v-model="gdprForm.reason"
                type="textarea"
                :rows="2"
                :placeholder="t('adminSettings.gdpr.reasonPlaceholder')"
                maxlength="500"
                show-word-limit
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="gdprExporting"
                :disabled="!gdprForm.userId"
                @click="handleGdprExport"
              >
                <el-icon><Download /></el-icon>
                {{ t('adminSettings.gdpr.exportBtn') }}
              </el-button>
              <el-button
                type="danger"
                :loading="gdprDeleting"
                :disabled="!gdprForm.userId || !gdprForm.reason"
                @click="openGdprDeleteDialog"
              >
                <el-icon><Delete /></el-icon>
                {{ t('adminSettings.gdpr.anonymizeBtn') }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- ISS-077: 安全配置 -->
      <el-tab-pane
        :label="t('adminSettings.tabs.security')"
        name="security"
      >
        <el-card>
          <template #header>
            <div class="header-row">
              <span class="card-title">{{ t('adminSettings.security.cardTitle') }}</span>
              <el-button
                type="primary"
                size="small"
                :loading="securitySaving"
                @click="saveSecurityConfig"
              >
                {{ t('common.save') }}
              </el-button>
            </div>
          </template>
          <el-form
            :model="securityForm"
            label-width="160px"
            class="security-form"
          >
            <el-form-item :label="t('adminSettings.security.passwordMinLength')">
              <el-input-number
                v-model="securityForm.password_min_length"
                :min="6"
                :max="128"
              />
            </el-form-item>
            <el-form-item :label="t('adminSettings.security.passwordRequireSpecial')">
              <el-switch v-model="securityForm.password_require_special" />
              <span class="form-hint">{{ t('adminSettings.security.passwordRequireSpecialHint') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSettings.security.tokenExpiry')">
              <el-input-number
                v-model="securityForm.token_expiry"
                :min="1"
                :max="10080"
              />
            </el-form-item>
            <el-form-item :label="t('adminSettings.security.rateLimit')">
              <el-input-number
                v-model="securityForm.rate_limit_per_minute"
                :min="1"
                :max="10000"
              />
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- ISS-077: 通知配置 -->
      <el-tab-pane
        :label="t('adminSettings.tabs.notification')"
        name="notification"
      >
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
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="thresholdFormVisible"
      :title="thresholdEditing ? t('adminSettings.thresholds.editDialogTitle') : t('adminSettings.thresholds.createDialogTitle')"
      width="480px"
      destroy-on-close
    >
      <el-form
        :model="thresholdForm"
        label-width="100px"
      >
        <el-form-item
          :label="t('adminSettings.thresholds.formLevel')"
          required
        >
          <el-input-number
            v-model="thresholdForm.level"
            :min="0"
            :max="10"
            :disabled="!!thresholdEditing"
          />
        </el-form-item>
        <el-form-item
          :label="t('adminSettings.thresholds.formLevelName')"
          required
        >
          <el-input v-model="thresholdForm.level_name" />
        </el-form-item>
        <el-form-item
          :label="t('adminSettings.thresholds.formMinScore')"
          required
        >
          <el-input-number
            v-model="thresholdForm.min_score"
            :min="0"
            :max="100"
            :precision="1"
          />
        </el-form-item>
        <el-form-item
          :label="t('adminSettings.thresholds.formMaxScore')"
          required
        >
          <el-input-number
            v-model="thresholdForm.max_score"
            :min="0"
            :max="100"
            :precision="1"
          />
        </el-form-item>
        <el-form-item
          :label="t('adminSettings.thresholds.formColor')"
          required
        >
          <el-input
            v-model="thresholdForm.color"
            placeholder="#d4923a"
          />
        </el-form-item>
        <el-form-item
          :label="t('adminSettings.thresholds.formActionRequired')"
          required
        >
          <el-input
            v-model="thresholdForm.action_required"
            type="textarea"
            :rows="2"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="thresholdFormVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="thresholdSaving"
          @click="submitThreshold"
        >
          {{ t('common.save') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="configFormVisible"
      :title="configEditing ? t('adminSettings.configs.editDialogTitle') : t('adminSettings.configs.createDialogTitle')"
      width="480px"
      destroy-on-close
    >
      <el-form
        :model="configForm"
        label-width="100px"
      >
        <el-form-item
          :label="t('adminSettings.configs.formKey')"
          required
        >
          <el-input
            v-model="configForm.config_key"
            :disabled="!!configEditing"
          />
        </el-form-item>
        <el-form-item
          :label="t('adminSettings.configs.formValue')"
          required
        >
          <el-input
            v-model="configValueJson"
            type="textarea"
            :rows="4"
            placeholder="{&quot;value&quot;: &quot;example&quot;}"
          />
        </el-form-item>
        <el-form-item :label="t('adminSettings.configs.formDescription')">
          <el-input v-model="configForm.description" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configFormVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="configSaving"
          @click="submitConfig"
        >
          {{ t('common.save') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ISS-074: GDPR 匿名化确认对话框 -->
    <el-dialog
      v-model="gdprDeleteVisible"
      :title="t('adminSettings.gdpr.deleteDialogTitle')"
      width="500px"
      destroy-on-close
    >
      <el-alert
        type="error"
        :closable="false"
        show-icon
        class="gdpr-alert"
      >
        <template #title>
          {{ t('adminSettings.gdpr.deleteDialogAlertTitle') }}
        </template>
        <template #default>
          {{ t('adminSettings.gdpr.deleteDialogAlertContent', { userId: gdprForm.userId }) }}
        </template>
      </el-alert>
      <div class="gdpr-confirm-reason">
        {{ t('adminSettings.gdpr.confirmReasonLabel') }}<strong>{{ gdprForm.reason }}</strong>
      </div>
      <el-form label-width="120px">
        <el-form-item :label="t('adminSettings.gdpr.confirmKeywordLabel')">
          <el-input
            v-model="gdprConfirmText"
            :placeholder="t('adminSettings.gdpr.confirmKeywordPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="gdprDeleteVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="danger"
          :loading="gdprDeleting"
          :disabled="gdprConfirmText !== t('adminSettings.gdpr.confirmKeyword')"
          @click="handleGdprDelete"
        >
          {{ t('adminSettings.gdpr.confirmAnonymizeBtn') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'AdminSettingsPage' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Download, Delete } from '@element-plus/icons-vue'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import { adminApi, type ThresholdItem, type ConfigItem, type ModelFeedbackItem } from '@/api/adminApi'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { getStoredToken } from '@/utils/authStorage' // ISS-008: 从 authStorage 获取 token

const { t } = useI18n()

const activeTab = ref('thresholds')

const thresholds = ref<ThresholdItem[]>([])
const thresholdLoading = ref(false)
const thresholdError = ref('')

const loadThresholds = async () => {
  thresholdLoading.value = true
  thresholdError.value = ''
  try {
    const data = await adminApi.listAdminThresholds()
    thresholds.value = data.items
  } catch (error) {
    thresholdError.value = normalizeHttpError(error, t('adminSettings.thresholds.loadFailed')).detail
  } finally {
    thresholdLoading.value = false
  }
}

const thresholdFormVisible = ref(false)
const thresholdSaving = ref(false)
const thresholdEditing = ref(false)
const thresholdForm = reactive({ level: 0, level_name: '', min_score: 0, max_score: 100, color: '#d4923a', action_required: '' })

const openThresholdCreate = () => {
  thresholdEditing.value = false
  thresholdForm.level = 0
  thresholdForm.level_name = ''
  thresholdForm.min_score = 0
  thresholdForm.max_score = 100
  thresholdForm.color = '#d4923a'
  thresholdForm.action_required = ''
  thresholdFormVisible.value = true
}

const openThresholdEdit = (row: ThresholdItem) => {
  thresholdEditing.value = true
  thresholdForm.level = row.level
  thresholdForm.level_name = row.level_name
  thresholdForm.min_score = row.min_score
  thresholdForm.max_score = row.max_score
  thresholdForm.color = row.color
  thresholdForm.action_required = row.action_required
  thresholdFormVisible.value = true
}

const submitThreshold = async () => {
  if (!thresholdForm.level_name.trim()) { ElMessage.warning(t('adminSettings.thresholds.errorLevelNameRequired')); return }
  if (thresholdForm.min_score > thresholdForm.max_score) { ElMessage.warning(t('adminSettings.thresholds.errorScoreRange')); return }
  thresholdSaving.value = true
  try {
    await adminApi.upsertAdminThreshold({ ...thresholdForm })
    ElMessage.success(t('adminSettings.thresholds.saved'))
    thresholdFormVisible.value = false
    loadThresholds()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('adminSettings.thresholds.saveFailed')).detail)
  } finally {
    thresholdSaving.value = false
  }
}

const configs = ref<ConfigItem[]>([])
const configLoading = ref(false)
const configError = ref('')

const loadConfigs = async () => {
  configLoading.value = true
  configError.value = ''
  try {
    const data = await adminApi.listAdminConfigs()
    configs.value = data.items
    // ISS-077: 同步加载安全配置和通知配置表单
    loadSecurityConfig()
    loadNotificationConfig()
  } catch (error) {
    configError.value = normalizeHttpError(error, t('adminSettings.configs.loadFailed')).detail
  } finally {
    configLoading.value = false
  }
}

const configFormVisible = ref(false)
const configSaving = ref(false)
const configEditing = ref(false)
const configForm = reactive({ config_key: '', description: '' })
const configValueJson = ref('{}')

const openConfigCreate = () => {
  configEditing.value = false
  configForm.config_key = ''
  configForm.description = ''
  configValueJson.value = '{}'
  configFormVisible.value = true
}

const openConfigEdit = (row: ConfigItem) => {
  configEditing.value = true
  configForm.config_key = row.config_key
  configForm.description = row.description || ''
  configValueJson.value = JSON.stringify(row.config_value, null, 2)
  configFormVisible.value = true
}

const submitConfig = async () => {
  if (!configForm.config_key.trim()) { ElMessage.warning(t('adminSettings.configs.errorKeyRequired')); return }
  let configValue: Record<string, unknown>
  try { configValue = JSON.parse(configValueJson.value) } catch { ElMessage.warning(t('adminSettings.configs.errorJsonInvalid')); return }
  configSaving.value = true
  try {
    await adminApi.upsertAdminConfig({ config_key: configForm.config_key, config_value: configValue, description: configForm.description || undefined })
    ElMessage.success(t('adminSettings.configs.saved'))
    configFormVisible.value = false
    loadConfigs()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('adminSettings.configs.saveFailed')).detail)
  } finally {
    configSaving.value = false
  }
}

// ===== ISS-077: 安全配置 / 通知配置 =====
// 从 configs 列表中按 key 提取值
const getConfigValue = <T,>(key: string, fallback: T): T => {
  const item = configs.value.find((c) => c.config_key === key)
  if (!item) return fallback
  const val = (item.config_value as Record<string, unknown>)?.value
  return (val as T) ?? fallback
}

const securityForm = reactive({
  password_min_length: 8,
  password_require_special: true,
  token_expiry: 60,
  rate_limit_per_minute: 60,
})
const securitySaving = ref(false)

const loadSecurityConfig = () => {
  securityForm.password_min_length = getConfigValue('password_min_length', 8)
  securityForm.password_require_special = getConfigValue('password_require_special', true)
  securityForm.token_expiry = getConfigValue('token_expiry', 60)
  securityForm.rate_limit_per_minute = getConfigValue('rate_limit_per_minute', 60)
}

const saveSecurityConfig = async () => {
  securitySaving.value = true
  try {
    await Promise.all([
      adminApi.upsertAdminConfig({ config_key: 'password_min_length', config_value: { value: securityForm.password_min_length } }),
      adminApi.upsertAdminConfig({ config_key: 'password_require_special', config_value: { value: securityForm.password_require_special } }),
      adminApi.upsertAdminConfig({ config_key: 'token_expiry', config_value: { value: securityForm.token_expiry } }),
      adminApi.upsertAdminConfig({ config_key: 'rate_limit_per_minute', config_value: { value: securityForm.rate_limit_per_minute } }),
    ])
    ElMessage.success(t('adminSettings.security.saved'))
    loadConfigs()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('adminSettings.security.saveFailed')).detail)
  } finally {
    securitySaving.value = false
  }
}

const notificationForm = reactive({
  notification_email_enabled: false,
  notification_sms_enabled: false,
  notification_webhook_url: '',
})
const notificationSaving = ref(false)

const loadNotificationConfig = () => {
  notificationForm.notification_email_enabled = getConfigValue('notification_email_enabled', false)
  notificationForm.notification_sms_enabled = getConfigValue('notification_sms_enabled', false)
  notificationForm.notification_webhook_url = getConfigValue('notification_webhook_url', '')
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
    loadConfigs()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('adminSettings.notification.saveFailed')).detail)
  } finally {
    notificationSaving.value = false
  }
}

const feedbacks = ref<ModelFeedbackItem[]>([])
const feedbackTotal = ref(0)
const feedbackPage = ref(1)
const feedbackPageSize = ref(10)
const feedbackLoading = ref(false)
const feedbackError = ref('')

const loadFeedbacks = async () => {
  feedbackLoading.value = true
  feedbackError.value = ''
  try {
    const data = await adminApi.listAdminFeedbacks({ page: feedbackPage.value, page_size: feedbackPageSize.value })
    feedbacks.value = data.items
    feedbackTotal.value = data.total
  } catch (error) {
    feedbackError.value = normalizeHttpError(error, t('adminSettings.feedbacks.loadFailed')).detail
  } finally {
    feedbackLoading.value = false
  }
}

// ===== ISS-074: GDPR 合规管理 =====
const gdprForm = reactive<{ userId: number | null; reason: string }>({
  userId: null,
  reason: ''
})
const gdprChecking = ref(false)
const gdprExporting = ref(false)
const gdprDeleting = ref(false)
const gdprDeleteVisible = ref(false)
const gdprConfirmText = ref('')
const gdprCheckResult = ref<{ ok: boolean; message: string } | null>(null)

// 校验目标用户 ID 基本格式（实际存在性由导出/删除接口返回 404 时反馈）
const checkUserExists = async () => {
  if (!gdprForm.userId || gdprForm.userId < 1) {
    gdprCheckResult.value = { ok: false, message: t('adminSettings.gdpr.checkUserIdInvalid') }
    return
  }
  gdprChecking.value = true
  gdprCheckResult.value = null
  try {
    // 通过尝试导出接口的 HEAD 不适用，这里用轻量的导出请求校验
    // 若用户不存在，export 接口返回 404；由于是流式响应，使用 HEAD 不可行，
    // 改用小型探针：fetch 导出接口并立即取消，仅观察 status code
    const controller = new AbortController()
    const token = getStoredToken() || '' // ISS-008: 从 authStorage 获取 token（sessionStorage）
    const res = await fetch(`/api/v1/admin/gdpr/export/${gdprForm.userId}`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal
    })
    // 立即中止流式下载，只关心 status
    controller.abort()
    if (res.status === 200) {
      gdprCheckResult.value = { ok: true, message: t('adminSettings.gdpr.checkUserOk') }
    } else if (res.status === 404) {
      gdprCheckResult.value = { ok: false, message: t('adminSettings.gdpr.checkUserNotFound') }
    } else if (res.status === 403) {
      gdprCheckResult.value = { ok: false, message: t('adminSettings.gdpr.checkUserNoPermission') }
    } else {
      gdprCheckResult.value = { ok: false, message: t('adminSettings.gdpr.checkFailed', { status: res.status }) }
    }
  } catch {
    // AbortController 中止会抛 AbortError，属预期行为
    gdprCheckResult.value = { ok: true, message: t('adminSettings.gdpr.checkUserOkAborted') }
  } finally {
    gdprChecking.value = false
  }
}

const handleGdprExport = async () => {
  if (!gdprForm.userId) return
  gdprExporting.value = true
  try {
    const blob = await adminApi.exportUserGdpr(gdprForm.userId)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `user_${gdprForm.userId}_data.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success(t('adminSettings.gdpr.exportSuccess'))
  } catch (error) {
    showHttpFeedback(error, t('adminSettings.gdpr.exportFailed'))
  } finally {
    gdprExporting.value = false
  }
}

const openGdprDeleteDialog = () => {
  if (!gdprForm.userId) {
    ElMessage.warning(t('adminSettings.gdpr.errorUserIdRequired'))
    return
  }
  if (!gdprForm.reason) {
    ElMessage.warning(t('adminSettings.gdpr.errorReasonRequired'))
    return
  }
  gdprConfirmText.value = ''
  gdprDeleteVisible.value = true
}

const handleGdprDelete = async () => {
  if (!gdprForm.userId || gdprConfirmText.value !== t('adminSettings.gdpr.confirmKeyword')) return
  gdprDeleting.value = true
  try {
    await adminApi.deleteUserGdpr(gdprForm.userId, {
      confirm: true,
      reason: gdprForm.reason
    })
    ElMessage.success(t('adminSettings.gdpr.anonymized'))
    gdprDeleteVisible.value = false
    gdprForm.userId = null
    gdprForm.reason = ''
    gdprCheckResult.value = null
  } catch (error) {
    showHttpFeedback(error, t('adminSettings.gdpr.anonymizeFailed'))
  } finally {
    gdprDeleting.value = false
  }
}

onMounted(() => {
  loadThresholds()
  loadConfigs()
  loadFeedbacks()
})
</script>

<style scoped>
.settings-page {
  padding: 0;
}

.card-title {
  font-weight: var(--font-weight-semibold);
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.config-value {
  font-family: monospace;
  font-size: var(--font-size-extra-small);
  color: var(--text-regular);
  word-break: break-all;
}

/* ISS-077: 安全配置 / 通知配置表单提示 */
.form-hint {
  margin-left: 12px;
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.security-form,
.notification-form {
  max-width: 640px;
}

.pager-wrap {
  margin-top: var(--spacing-md);
  display: flex;
  justify-content: flex-end;
}

/* ISS-074: GDPR 合规区块样式 */
.gdpr-alert {
  margin-bottom: var(--spacing-md);
}

.gdpr-form {
  max-width: 640px;
}

.gdpr-check-result {
  margin-left: 12px;
  font-size: var(--font-size-small);
}

.gdpr-check-result.ok {
  color: var(--color-success, #67c23a);
}

.gdpr-check-result.err {
  color: var(--color-danger, #f56c6c);
}

.gdpr-confirm-reason {
  margin: 12px 0;
  padding: 8px 12px;
  /* ISS-023 修复：使用 --bg-page 令牌，原 --bg-color-page 未定义 */
  background: var(--bg-page, #f5f7fa);
  border-radius: 4px;
  font-size: var(--font-size-small);
}
</style>

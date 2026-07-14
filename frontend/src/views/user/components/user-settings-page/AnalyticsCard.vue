<template>
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
</template>

<script setup lang="ts">
defineOptions({ name: 'AnalyticsCard' })
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
// P1-5 埋点与隐私闭环：分析同意管理
import { useAnalytics } from '@/composables/useAnalytics'

const { t } = useI18n()

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

onMounted(() => {
  refreshConsent()
})
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.section-card {
  margin-top: var(--spacing-lg);
}

.gdpr-alert {
  margin-bottom: var(--spacing-md);
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
</style>

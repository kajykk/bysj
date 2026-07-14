<template>
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
</template>

<script setup lang="ts">
defineOptions({ name: 'SecurityTab' })
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

// ISS-077: 安全配置
const securityForm = reactive({
  password_min_length: 8,
  password_require_special: true,
  token_expiry: 60,
  rate_limit_per_minute: 60,
})
const securitySaving = ref(false)

const loadSecurityConfig = () => {
  securityForm.password_min_length = getConfigValue(props.configs, 'password_min_length', 8)
  securityForm.password_require_special = getConfigValue(props.configs, 'password_require_special', true)
  securityForm.token_expiry = getConfigValue(props.configs, 'token_expiry', 60)
  securityForm.rate_limit_per_minute = getConfigValue(props.configs, 'rate_limit_per_minute', 60)
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
    emit('reload')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('adminSettings.security.saveFailed')).detail)
  } finally {
    securitySaving.value = false
  }
}

// configs 由父组件加载，加载完成后同步表单值
watch(() => props.configs, () => {
  loadSecurityConfig()
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

/* ISS-077: 安全配置表单提示 */
.form-hint {
  margin-left: 12px;
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.security-form {
  max-width: 640px;
}
</style>

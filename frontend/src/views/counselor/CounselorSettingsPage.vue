<template>
  <div class="settings-page">
    <el-row :gutter="16">
      <el-col
        :xs="24"
        :md="12"
      >
        <el-card>
          <template #header>
            <span class="card-title">{{ t('counselorSettings.bindCodeCardTitle') }}</span>
          </template>
          <div
            v-if="bindCodeLoading"
            class="skeleton-padding"
          >
            <el-skeleton
              :rows="2"
              animated
            />
          </div>
          <template v-else>
            <div class="bind-code-display">
              <span class="bind-code-text">{{ counselorBindCode || '—' }}</span>
              <el-tag
                v-if="bindCodeStatusLabel"
                :type="bindCodeStatusType"
                effect="light"
              >
                {{ bindCodeStatusLabel }}
              </el-tag>
              <el-button
                type="primary"
                link
                @click="copyBindCode"
              >
                {{ t('counselorSettings.btnCopy') }}
              </el-button>
            </div>
            <div class="bind-tip">
              <el-icon><InfoFilled /></el-icon>
              <span>{{ t('counselorSettings.bindTip') }}</span>
            </div>
            <div class="refresh-row">
              <el-button
                type="warning"
                plain
                size="small"
                :loading="refreshCodeLoading"
                @click="handleRefreshCode"
              >
                {{ t('counselorSettings.btnRefreshBindCode') }}
              </el-button>
            </div>
          </template>
        </el-card>
      </el-col>

      <el-col
        :xs="24"
        :md="12"
      >
        <el-card>
          <template #header>
            <span class="card-title">{{ t('counselorSettings.profileCardTitle') }}</span>
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
                :model-value="t('counselorSettings.profileRoleCounselor')"
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
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="section-card">
          <template #header>
            <span class="card-title">{{ t('counselorSettings.passwordCardTitle') }}</span>
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
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'CounselorSettingsPage' })
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import { counselorApi } from '@/api/counselorApi'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { setStoredAuth } from '@/utils/authStorage'

const { t } = useI18n()
const auth = useAuthStore()

const bindCodeLoading = ref(true)
const counselorBindCode = ref('')
const bindCodeStatus = ref<'placeholder' | 'active' | 'inactive'>('placeholder')
const refreshCodeLoading = ref(false)

const bindCodeStatusLabel = computed(() => {
  if (bindCodeStatus.value === 'active') return t('counselorSettings.bindCodeStatusActive')
  if (bindCodeStatus.value === 'placeholder') return t('counselorSettings.bindCodeStatusPlaceholder')
  return t('counselorSettings.bindCodeStatusInactive')
})

const bindCodeStatusType = computed(() => {
  if (bindCodeStatus.value === 'active') return 'success'
  if (bindCodeStatus.value === 'placeholder') return 'warning'
  return 'info'
})

const loadCounselorBindCode = async () => {
  bindCodeLoading.value = true
  try {
    const data = await counselorApi.getCounselorBindCode()
    counselorBindCode.value = data.bind_code
    bindCodeStatus.value = 'active'
  } catch {
    counselorBindCode.value = ''
    bindCodeStatus.value = 'inactive'
  } finally {
    bindCodeLoading.value = false
  }
}

const copyBindCode = async () => {
  if (!counselorBindCode.value) return
  try {
    await navigator.clipboard.writeText(counselorBindCode.value)
    ElMessage.success(t('counselorSettings.bindCodeCopied'))
  } catch {
    ElMessage.warning(t('counselorSettings.bindCodeCopyFailed'))
  }
}

// ISS-035 修复：刷新绑定码会使原绑定码失效，属于销毁性操作，确认框类型由 warning 调整为 error
const handleRefreshCode = async () => {
  try {
    await ElMessageBox.confirm(t('counselorSettings.bindCodeRefreshConfirm'), t('counselorSettings.bindCodeRefreshConfirmTitle'), { type: 'error' })
  } catch {
    return
  }
  refreshCodeLoading.value = true
  try {
    const data = await counselorApi.refreshCounselorBindCode()
    counselorBindCode.value = data.bind_code
    bindCodeStatus.value = 'active'
    ElMessage.success(t('counselorSettings.bindCodeRefreshed'))
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('userSettings.binding.bindFailed')).detail)
  } finally {
    refreshCodeLoading.value = false
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

onMounted(() => {
  loadCounselorBindCode()
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

.bind-code-display {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.bind-code-text {
  font-size: 28px;
  font-weight: var(--font-weight-bold);
  letter-spacing: 4px;
  color: var(--primary-color);
  font-family: 'Courier New', Courier, monospace;
}

.bind-tip {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-sm);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: 1.6;
}

.bind-tip .el-icon {
  margin-top: 3px;
  flex-shrink: 0;
}

.refresh-row {
  margin-top: var(--spacing-md);
}

.section-card {
  margin-top: var(--spacing-lg);
}
</style>

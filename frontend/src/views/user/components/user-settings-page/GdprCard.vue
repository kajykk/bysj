<template>
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
</template>

<script setup lang="ts">
defineOptions({ name: 'GdprCard' })
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { userApi } from '@/api/userApi'
import { normalizeHttpError } from '@/utils/errorPolicy'

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()

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

@media (max-width: 768px) {
  .gdpr-action-row {
    flex-direction: column;
    align-items: stretch;
  }

  .gdpr-action-row .el-button {
    width: 100%;
  }
}
</style>

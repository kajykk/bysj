<template>
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
</template>

<script setup lang="ts">
defineOptions({ name: 'GdprTab' })
import { reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Download, Delete } from '@element-plus/icons-vue'
import { adminApi } from '@/api/adminApi'
import { buildApiUrl } from '@/api/base'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { getStoredToken } from '@/utils/authStorage' // ISS-008: 从 authStorage 获取 token

const { t } = useI18n()

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
    // AUDIT-2026-09-30-P1-16：改用 HEAD 探针 + buildApiUrl。
    //
    // 原实现（GET + AbortController）有两处缺陷：
    // 1) fetch 在响应头到达时即 resolve，随后的 abort() 不会进入 catch —— 那个
    //    "AbortError 属预期行为"的分支实际上永远走不到；
    // 2) 真正进入 catch 的是断网 / 超时 / 连接重置，而 catch 里一律判定 ok:true，
    //    管理员据此会误判"用户存在"并继续执行 GDPR 匿名化（不可逆操作）。
    //
    // HEAD 由 Starlette 对 GET 路由自动开放（routing.py:233-234），且
    // responses.py 对 HEAD 只回响应头、不消费 body，因此无需 abort 即可
    // 拿到 200 / 404 / 403，也不会真的导出一份完整数据。
    const token = getStoredToken() || '' // ISS-008: 从 authStorage 获取 token（sessionStorage）
    const res = await fetch(buildApiUrl(`/admin/gdpr/export/${gdprForm.userId}`), {
      method: 'HEAD',
      headers: { Authorization: `Bearer ${token}` }
    })
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
    // 断网 / 超时 / CORS / 连接重置：一律判为"未能确认"，绝不可断言用户存在
    gdprCheckResult.value = { ok: false, message: t('adminSettings.gdpr.checkNetworkError') }
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

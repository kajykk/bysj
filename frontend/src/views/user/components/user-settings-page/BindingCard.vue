<template>
  <el-card>
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
</template>

<script setup lang="ts">
defineOptions({ name: 'BindingCard' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { userApi, type UserBindingInfo } from '@/api/userApi'
import type { BindCounselorResult } from '@/api/userBindingApi'
import { normalizeHttpError } from '@/utils/errorPolicy'
// P2-A 修复：复用 formatUtils 的 formatDate，避免本地重复定义
import { formatDate } from '@/utils/formatUtils'

const { t } = useI18n()
const auth = useAuthStore()

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

onMounted(() => {
  loadBinding()
})
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.skeleton-padding {
  padding: var(--spacing-xl);
}

.unbind-row {
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
</style>

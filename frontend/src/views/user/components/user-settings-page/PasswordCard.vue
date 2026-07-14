<template>
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
</template>

<script setup lang="ts">
defineOptions({ name: 'PasswordCard' })
import { reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { authApi } from '@/api/auth'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { checkPasswordBytes } from '@/utils/passwordValidation'

const { t } = useI18n()

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
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.section-card {
  margin-top: var(--spacing-lg);
}
</style>

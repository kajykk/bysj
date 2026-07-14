<template>
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
</template>

<script setup lang="ts">
defineOptions({ name: 'ProfileCard' })
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { setStoredAuth } from '@/utils/authStorage'

const { t } = useI18n()
const auth = useAuthStore()

const roleLabel = computed(() => {
  if (auth.role === 'admin') return t('userSettings.roles.admin')
  if (auth.role === 'counselor') return t('userSettings.roles.counselor')
  return t('userSettings.roles.user')
})

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
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.section-card {
  margin-top: var(--spacing-lg);
}

.reset-btn {
  margin-left: var(--spacing-sm);
}
</style>

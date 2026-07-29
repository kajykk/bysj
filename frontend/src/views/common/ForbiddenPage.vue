<template>
  <ErrorPage code="403">
    <template #actions>
      <el-button
        type="primary"
        size="large"
        :icon="HomeFilled"
        @click="goHome"
      >
        {{ t('error.goHome') }}
      </el-button>
      <el-button
        size="large"
        :icon="Back"
        @click="goBack"
      >
        {{ t('error.goBack') }}
      </el-button>
    </template>
  </ErrorPage>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { HomeFilled, Back } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import ErrorPage from '@/components/common/ErrorPage.vue'

const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()

const goHome = () => {
  const role = auth.role
  const homePath = role === 'admin'
    ? '/admin/dashboard'
    : role === 'counselor'
      ? '/counselor/dashboard'
      : '/user/dashboard'
  router.push(homePath)
}

const goBack = () => {
  router.back()
}
</script>

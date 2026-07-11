<template>
  <div class="forbidden-page">
    <el-result
      icon="warning"
      title="403"
      sub-title="抱歉，您没有权限访问此页面"
    >
      <template #extra>
        <el-button
          type="primary"
          @click="goHome"
        >
          返回首页
        </el-button>
        <el-button @click="goBack">
          返回上一页
        </el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

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

<style scoped>
.forbidden-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
</style>

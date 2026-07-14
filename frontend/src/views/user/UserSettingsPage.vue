<template>
  <div class="settings-page">
    <el-row :gutter="16">
      <el-col
        :xs="24"
        :md="12"
      >
        <AlertSettingsCard />
        <RiskThresholdCard />
      </el-col>

      <el-col
        :xs="24"
        :md="12"
      >
        <BindingCard v-if="auth.role === 'user'" />
        <ProfileCard />
        <PasswordCard />
        <GdprCard />
        <AnalyticsCard />
        <CrisisCard />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'UserSettingsPage' })
import { useAuthStore } from '@/stores/auth'
import AlertSettingsCard from './components/user-settings-page/AlertSettingsCard.vue'
import BindingCard from './components/user-settings-page/BindingCard.vue'
import ProfileCard from './components/user-settings-page/ProfileCard.vue'
import PasswordCard from './components/user-settings-page/PasswordCard.vue'
import GdprCard from './components/user-settings-page/GdprCard.vue'
import AnalyticsCard from './components/user-settings-page/AnalyticsCard.vue'
import RiskThresholdCard from './components/user-settings-page/RiskThresholdCard.vue'
import CrisisCard from './components/user-settings-page/CrisisCard.vue'

const auth = useAuthStore()
</script>

<style scoped>
.settings-page {
  padding: 0;
}
</style>

<template>
  <div class="settings-page">
    <!-- BLANK-10 修复：原 el-row 双栏左 2 卡 / 右 6 卡严重失衡，左列下方大面积空白。
         改为 CSS Grid 两列自动行布局，并按"高卡配矮卡"重排顺序，
         每行高度由较高卡决定，消除失衡留白 -->
    <div class="settings-grid">
      <AlertSettingsCard />
      <BindingCard v-if="auth.role === 'user'" />
      <RiskThresholdCard />
      <ProfileCard />
      <GdprCard />
      <PasswordCard />
      <AnalyticsCard />
      <CrisisCard />
    </div>
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

.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-md);
  align-items: start;
}

/* 卡片自带的堆叠 margin 在 Grid 上下文中会破坏对齐，统一交由 grid gap 控制间距 */
.settings-grid :deep(.section-card) {
  margin-top: 0;
}

/* 与 Element Plus md 断点（≥768px 双列）保持一致 */
@media (max-width: 767px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<template>
  <nav
    v-if="isMobile"
    class="bottom-nav"
    :aria-label="t('common.mainNav')"
  >
    <router-link
      v-for="item in navItems"
      :key="item.path"
      :to="item.path"
      class="bottom-nav-item"
      :class="{ active: route.path === item.path }"
      :aria-label="t(item.label)"
      :aria-current="route.path === item.path ? 'page' : undefined"
    >
      <el-icon
        :size="20"
        aria-hidden="true"
      >
        <component :is="item.icon" />
      </el-icon>
      <span class="bottom-nav-label">{{ t(item.label) }}</span>
    </router-link>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useAuthStore } from '@/stores/auth'
import {
  HomeFilled,
  Document,
  Warning,
  User,
  Setting,
  Bell,
  DataLine,
  Files
} from '@element-plus/icons-vue'

const route = useRoute()
const { isMobile } = useBreakpoint()
const { t } = useI18n()
const authStore = useAuthStore()

// ISS-034 修复：根据用户角色返回对应的底部导航项
// admin 角色补充专属导航项，原仅 user/counselor 共用 5 项
const navItems = computed(() => {
  const role = authStore.role
  if (role === 'admin') {
    return [
      { path: '/admin/dashboard', icon: DataLine, label: 'nav.admin.home' },
      { path: '/admin/crisis-events', icon: Warning, label: 'nav.admin.crisisEvents' },
      { path: '/admin/alerts', icon: Bell, label: 'nav.admin.alerts' },
      { path: '/admin/operation-logs', icon: Files, label: 'nav.admin.operationLogs' },
      { path: '/admin/settings', icon: Setting, label: 'nav.admin.settings' }
    ]
  }
  if (role === 'counselor') {
    return [
      { path: '/counselor/dashboard', icon: HomeFilled, label: 'nav.counselor.home' },
      { path: '/counselor/warnings', icon: Warning, label: 'nav.warning' },
      { path: '/counselor/users', icon: User, label: 'nav.userManagement' },
      { path: '/counselor/reviews', icon: Document, label: 'nav.counselor.reviews' },
      { path: '/counselor/settings', icon: Setting, label: 'nav.settings' }
    ]
  }
  // 默认 user 角色
  return [
    { path: '/user/dashboard', icon: HomeFilled, label: 'nav.dashboard' },
    { path: '/user/risk', icon: Document, label: 'nav.riskAssessment' },
    { path: '/user/warnings', icon: Warning, label: 'nav.warning' },
    { path: '/user/intervention', icon: Files, label: 'nav.user.intervention' },
    { path: '/user/settings', icon: Setting, label: 'nav.settings' }
  ]
})
</script>

<style scoped lang="scss">
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 56px;
  background: var(--bg-primary);
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: space-around;
  align-items: center;
  z-index: 100;
  padding-bottom: env(safe-area-inset-bottom);
}

.bottom-nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  color: var(--text-secondary);
  text-decoration: none;
  /* ISS-037 修复：字号从 10px 提升至 12px，符合最小可读字号规范 */
  font-size: var(--font-size-extra-small);
  transition: color 0.2s;
  min-width: 44px;
  min-height: 44px;

  &.active {
    color: var(--primary-color);
  }
}

.bottom-nav-label {
  font-size: var(--font-size-extra-small);
}
</style>

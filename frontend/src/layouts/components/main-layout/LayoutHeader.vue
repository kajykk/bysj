<template>
  <el-header class="layout-header">
    <div class="header-left">
      <!-- VIS-015 修复：移动端汉堡菜单按钮，用于展开被收起的侧边栏 -->
      <el-button
        class="mobile-menu-btn"
        :aria-label="t('layout.expand')"
        circle
        size="small"
        @click="$emit('toggle-sidebar')"
      >
        <el-icon><Menu /></el-icon>
      </el-button>
      <BreadcrumbNav />
    </div>
    <div class="header-right">
      <el-badge
        :is-dot="hasNewWarning"
        class="warning-badge"
        @click="$emit('go-warnings')"
      >
        <el-button
          size="small"
          :icon="BellIcon"
          circle
          :aria-label="hasNewWarning ? t('layout.newWarning') : t('layout.noWarning')"
        />
      </el-badge>
      <HelpCenter :on-restart-onboarding="onRestartOnboarding" />
      <el-tag>{{ roleLabel }}</el-tag>
      <span>{{ userName }}</span>
      <el-button
        size="small"
        @click="$emit('logout')"
      >
        {{ t('layout.logout') }}
      </el-button>
    </div>
  </el-header>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Bell, Menu } from '@element-plus/icons-vue'
import BreadcrumbNav from '@/components/common/BreadcrumbNav.vue'
import HelpCenter from '@/components/common/HelpCenter.vue'

defineProps<{
  roleLabel: string
  hasNewWarning: boolean
  userName: string
  onRestartOnboarding: () => void
}>()

defineEmits<{
  (e: 'go-warnings'): void
  (e: 'logout'): void
  (e: 'toggle-sidebar'): void
}>()

const BellIcon = Bell
const { t } = useI18n()
</script>

<style scoped>
.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border-lighter);
  background: var(--bg-primary);
  box-shadow: 0 1px 3px rgba(46, 111, 168, 0.04);
}

.header-left {
  font-weight: var(--font-weight-semibold);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

/* VIS-015 修复：移动端汉堡菜单按钮 - 桌面端隐藏，移动端显示 */
.mobile-menu-btn {
  display: none;
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  font-size: var(--font-size-small);
  color: var(--text-regular);
}

.warning-badge {
  cursor: pointer;
}

/* 响应式：移动端头部紧凑布局 */
@media (max-width: 768px) {
  /* VIS-015 修复：移动端显示汉堡菜单按钮 */
  .mobile-menu-btn {
    display: inline-flex;
  }

  /* 移动端头部右侧紧凑布局 */
  /* ISS-107 修复：小屏下隐藏 .header-right 内的 span（用户名），避免与按钮挤压 */
  .header-right {
    gap: var(--spacing-sm);
  }

  .header-right span {
    display: none;
  }
}
</style>

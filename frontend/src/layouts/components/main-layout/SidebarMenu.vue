<template>
  <el-aside
    :width="asideWidth"
    class="layout-aside"
    :class="{ collapsed: layout.sidebarCollapsed }"
  >
    <div class="logo">
      <span v-if="!layout.sidebarCollapsed">{{ t('layout.appTitle') }}</span>
      <el-icon
        v-else
        :size="20"
      >
        <Bell />
      </el-icon>
    </div>
    <el-menu
      :default-active="activePath"
      router
      :collapse="layout.sidebarCollapsed"
      :collapse-transition="false"
    >
      <template
        v-for="section in menus"
        :key="section.key"
      >
        <el-menu-item
          v-if="!layout.sidebarCollapsed"
          :index="section.first?.path || '/'"
          class="menu-section-label"
          disabled
        >
          <template #title>
            {{ t(section.labelKey) }}
          </template>
        </el-menu-item>
        <el-tooltip
          v-for="item in section.items"
          :key="item.path"
          :content="t(item.titleKey)"
          :disabled="!layout.sidebarCollapsed"
          placement="right"
        >
          <el-menu-item
            :index="item.path"
            :data-tour="item.tourTarget"
          >
            <el-icon v-if="item.icon">
              <component :is="item.icon" />
            </el-icon>
            <template #title>
              {{ t(item.titleKey) }}
            </template>
          </el-menu-item>
        </el-tooltip>
      </template>
    </el-menu>
    <div
      class="collapse-btn"
      role="button"
      tabindex="0"
      :aria-label="layout.sidebarCollapsed ? t('layout.expand') : t('layout.collapse')"
      :aria-expanded="!layout.sidebarCollapsed"
      @click="layout.toggleSidebar"
      @keyup.enter="layout.toggleSidebar"
      @keyup.space.prevent="layout.toggleSidebar"
    >
      <el-icon>
        <Fold v-if="!layout.sidebarCollapsed" />
        <Expand v-else />
      </el-icon>
    </div>
    <div
      v-if="!layout.sidebarCollapsed"
      class="version-info"
    >
      v3.1.0
    </div>
  </el-aside>

  <!-- VIS-015 修复：移动端侧边栏遮罩层，点击关闭侧边栏 -->
  <div
    v-if="!layout.sidebarCollapsed"
    class="sidebar-backdrop"
    @click="layout.setSidebarCollapsed(true)"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Bell, Fold, Expand } from '@element-plus/icons-vue'
import { useLayoutStore } from '@/stores/layout'
import type { MenuSection } from './useLayoutMenu'

defineProps<{
  activePath: string
  menus: MenuSection[]
}>()

const { t } = useI18n()
const layout = useLayoutStore()

const asideWidth = computed(() => layout.sidebarCollapsed ? '64px' : '220px')
</script>

<style scoped>
.layout-aside {
  border-right: 1px solid var(--border-lighter);
  background: var(--bg-primary);
  transition: width var(--transition-duration) var(--transition-ease-out);
  position: relative;
  box-shadow: 1px 0 8px rgba(46, 111, 168, 0.04);
}

.layout-aside :deep(.el-menu) {
  border-right: none;
  padding: var(--spacing-sm) var(--spacing-xs);
}

.layout-aside :deep(.el-menu-item) {
  border-radius: var(--radius-base);
  margin-bottom: 2px;
  transition: background var(--transition-fast) var(--transition-timing),
    color var(--transition-fast) var(--transition-timing);
}

.layout-aside :deep(.el-menu-item:hover) {
  background: var(--primary-surface);
}

.layout-aside :deep(.el-menu-item.is-active) {
  background: var(--primary-surface);
  color: var(--primary-color);
  font-weight: var(--font-weight-medium);
}

.menu-section-label {
  font-size: var(--font-size-extra-small);
  font-weight: var(--font-weight-semibold);
  color: var(--text-placeholder);
  text-transform: uppercase;
  letter-spacing: var(--letter-spacing-wider);
  cursor: default;
  pointer-events: none;
  padding: var(--spacing-md) var(--spacing-sm) var(--spacing-xs);
  height: auto;
  line-height: var(--line-height-tight);
}

.menu-section-label:hover {
  background: transparent;
}

.layout-aside.collapsed .logo {
  padding: 0;
}

.logo {
  height: var(--layout-header-height);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-medium);
  letter-spacing: var(--letter-spacing-tight);
  color: var(--primary-color);
  border-bottom: 1px solid var(--border-extra-light);
  overflow: hidden;
  white-space: nowrap;
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.collapse-btn {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-top: 1px solid var(--border-lighter);
  background: var(--bg-primary);
  color: var(--text-secondary);
  transition: background var(--transition-fast) var(--transition-timing),
    color var(--transition-fast) var(--transition-timing);
}

.collapse-btn:hover {
  background: var(--primary-surface);
  color: var(--primary-color);
}

.collapse-btn:active {
  background: var(--primary-light);
}

.version-info {
  position: absolute;
  bottom: 40px;
  left: 0;
  right: 0;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  letter-spacing: var(--letter-spacing-wide);
  border-top: 1px solid var(--border-lighter);
}

/* VIS-015 修复：侧边栏遮罩层 - 桌面端隐藏，移动端显示 */
.sidebar-backdrop {
  display: none;
}

/* 响应式：移动端侧边栏优化 */
@media (max-width: 768px) {
  .layout-aside {
    position: fixed;
    z-index: 100;
    height: 100dvh;
    transform: translateX(0);
    transition: transform var(--transition-duration) var(--transition-ease-out);
  }

  .layout-aside.collapsed {
    transform: translateX(-100%);
    width: var(--layout-sidebar-width) !important;
  }

  /* VIS-015 修复：移动端侧边栏打开时显示遮罩层 */
  .sidebar-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    z-index: 99;
    animation: backdrop-fade-in var(--transition-fast) var(--transition-ease-out);
  }

  @keyframes backdrop-fade-in {
    from { opacity: 0; }
    to { opacity: 1; }
  }
}
</style>

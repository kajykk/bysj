<template>
  <el-aside
    :width="asideWidth"
    class="layout-aside"
    :class="{ collapsed: layout.sidebarCollapsed }"
  >
    <div class="logo">
      <!-- UI 升级 v3.2: 图形 Mark - 双叶护心,传递"评估+干预合围守护"的品牌语义 -->
      <svg
        class="logo-mark"
        viewBox="0 0 32 32"
        aria-hidden="true"
      >
        <defs>
          <linearGradient
            id="logo-mark-gradient"
            x1="0"
            y1="0"
            x2="1"
            y2="1"
          >
            <stop
              offset="0%"
              stop-color="var(--primary-400, #588cb9)"
            />
            <stop
              offset="100%"
              stop-color="var(--primary-600, #255986)"
            />
          </linearGradient>
        </defs>
        <path
          d="M16 6 C 10 10, 8 16, 16 26 C 24 16, 22 10, 16 6 Z"
          fill="url(#logo-mark-gradient)"
        />
        <path
          d="M16 12 C 13 14, 12 17, 16 22 C 20 17, 19 14, 16 12 Z"
          fill="rgba(255,255,255,0.4)"
        />
      </svg>
      <div
        v-if="!layout.sidebarCollapsed"
        class="logo-text-block"
      >
        <span class="logo-title">{{ t('layout.appTitle') }}</span>
        <span class="logo-subtitle">{{ t('layout.appSubtitle', '心理健康守护') }}</span>
      </div>
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
        <!-- 折叠态:用细分隔线代替分组标签,保留视觉分隔但不占位 -->
        <div
          v-else
          class="menu-section-divider"
          role="separator"
          :aria-label="t(section.labelKey)"
        />
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
            :class="{ 'has-badge': item.badge }"
          >
            <el-icon v-if="item.icon">
              <component :is="item.icon" />
            </el-icon>
            <template #title>
              {{ t(item.titleKey) }}
            </template>
            <!-- UI 升级 v3.2: 未读数徽章 - 显示在菜单项右侧 -->
            <span
              v-if="item.badge && !layout.sidebarCollapsed"
              class="menu-badge"
              :class="`menu-badge--${item.badgeVariant || 'danger'}`"
            >
              {{ item.badge > 99 ? '99+' : item.badge }}
            </span>
            <!-- 折叠态:徽章显示为小圆点 -->
            <span
              v-else-if="item.badge && layout.sidebarCollapsed"
              class="menu-badge-dot"
              :class="`menu-badge-dot--${item.badgeVariant || 'danger'}`"
              :aria-label="t('layout.unreadCount', { count: item.badge })"
            />
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
      v3.2.0
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
import { Fold, Expand } from '@element-plus/icons-vue'
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
  display: flex;
  flex-direction: column;
}

.layout-aside :deep(.el-menu) {
  border-right: none;
  padding: var(--spacing-sm) var(--spacing-xs);
  flex: 1;
}

.layout-aside :deep(.el-menu-item) {
  border-radius: var(--radius-base);
  margin-bottom: 2px;
  transition: background var(--transition-fast) var(--transition-timing),
    color var(--transition-fast) var(--transition-timing);
  position: relative;
}

.layout-aside :deep(.el-menu-item:hover) {
  background: var(--primary-surface);
}

/* UI 升级 v3.2: 激活态增加角色强调色色条 - 三端视觉差异化 */
.layout-aside :deep(.el-menu-item.is-active) {
  background: var(--primary-surface);
  color: var(--primary-color);
  font-weight: var(--font-weight-medium);
}

.layout-aside :deep(.el-menu-item.is-active)::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 2px 2px 0;
  background: var(--role-accent-current, var(--primary-color));
  transition: background var(--transition-fast) var(--transition-timing);
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

/* UI 升级 v3.2: 折叠态分组分隔线 - 代替丢失的分组标签 */
.menu-section-divider {
  height: 1px;
  background: var(--border-lighter);
  margin: var(--spacing-sm) var(--spacing-xs);
}

.layout-aside.collapsed .logo {
  padding: 0;
}

.logo {
  height: var(--layout-header-height);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 12px;
  border-bottom: 1px solid var(--border-extra-light);
  overflow: hidden;
  white-space: nowrap;
}

/* UI 升级 v3.2: Logo 图形 Mark */
.logo-mark {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}

.logo-text-block {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
  min-width: 0;
}

.logo-title {
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-base);
  letter-spacing: var(--letter-spacing-tight);
  color: var(--primary-color);
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  overflow: hidden;
  text-overflow: ellipsis;
}

.logo-subtitle {
  font-size: 10px;
  color: var(--text-secondary);
  letter-spacing: var(--letter-spacing-wide);
  font-weight: var(--font-weight-regular);
}

/* UI 升级 v3.2: 未读数徽章 */
.menu-badge {
  position: absolute;
  top: 6px;
  right: 8px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
  text-align: center;
  box-shadow: 0 0 0 2px var(--bg-primary);
  pointer-events: none;
}

.menu-badge--danger {
  background: var(--danger-color);
  color: #fff;
}

.menu-badge--warning {
  background: var(--warning-color);
  color: #fff;
}

.menu-badge--primary {
  background: var(--primary-color);
  color: #fff;
}

/* 折叠态徽章 - 小圆点 */
.menu-badge-dot {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  box-shadow: 0 0 0 2px var(--bg-primary);
  pointer-events: none;
}

.menu-badge-dot--danger { background: var(--danger-color); }
.menu-badge-dot--warning { background: var(--warning-color); }
.menu-badge-dot--primary { background: var(--primary-color); }

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

.collapse-btn:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: -2px;
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

/* 减少动效偏好:角色色条过渡关闭 */
@media (prefers-reduced-motion: reduce) {
  .layout-aside :deep(.el-menu-item.is-active)::before {
    transition: none;
  }
}
</style>

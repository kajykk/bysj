<template>
  <el-header class="layout-header">
    <!-- 左:导航上下文 -->
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

    <!-- 右:个人区(按"通知→帮助→用户"顺序,关键操作突出) -->
    <div class="header-right">
      <!-- 预警通知 - 升级为数字徽章 -->
      <el-badge
        :value="warningCount"
        :max="99"
        :hidden="warningCount === 0"
        class="warning-badge"
        @click="$emit('go-warnings')"
      >
        <el-button
          size="small"
          :icon="BellIcon"
          circle
          :aria-label="warningCount > 0 ? t('layout.newWarningCount', { count: warningCount }) : t('layout.noWarning')"
        />
      </el-badge>
      <HelpCenter :on-restart-onboarding="onRestartOnboarding" />

      <!-- UI 升级 v3.2: 用户菜单 - 头像+下拉,聚合设置/主题/引导/退出 -->
      <el-dropdown
        trigger="click"
        @command="handleCommand"
      >
        <div
          class="user-chip"
          role="button"
          tabindex="0"
          :aria-label="t('layout.userMenuAria', { name: userName, role: roleLabel })"
          @keydown.enter="$event.target.click()"
          @keydown.space.prevent="$event.target.click()"
        >
          <div
            class="user-avatar"
            :data-role="currentRole"
            aria-hidden="true"
          >
            {{ userInitials }}
          </div>
          <div class="user-meta">
            <div class="user-name">
              {{ userName }}
            </div>
            <div class="user-role">
              {{ roleLabel }}
            </div>
          </div>
          <el-icon class="user-caret">
            <ArrowDown />
          </el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="settings">
              <el-icon><Setting /></el-icon>
              {{ t('layout.userMenuSettings') }}
            </el-dropdown-item>
            <el-dropdown-item command="theme">
              <el-icon><Brush /></el-icon>
              {{ t('layout.userMenuTheme') }}
            </el-dropdown-item>
            <el-dropdown-item command="onboarding">
              <el-icon><QuestionFilled /></el-icon>
              {{ t('layout.userMenuOnboarding') }}
            </el-dropdown-item>
            <el-dropdown-item
              divided
              command="logout"
            >
              <el-icon><SwitchButton /></el-icon>
              {{ t('layout.logout') }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </el-header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Bell, Menu, ArrowDown, Setting, Brush, QuestionFilled, SwitchButton } from '@element-plus/icons-vue'
import BreadcrumbNav from '@/components/common/BreadcrumbNav.vue'
import HelpCenter from '@/components/common/HelpCenter.vue'

const props = defineProps<{
  roleLabel: string
  hasNewWarning: boolean
  warningCount?: number
  userName: string
  currentRole?: string
  onRestartOnboarding: () => void
}>()

const emit = defineEmits<{
  (e: 'go-warnings'): void
  (e: 'logout'): void
  (e: 'toggle-sidebar'): void
  (e: 'go-settings'): void
  (e: 'toggle-theme'): void
}>()

const BellIcon = Bell
const { t } = useI18n()

// 兼容旧 props: 优先使用 warningCount,回退到 hasNewWarning 的 0/1
const warningCount = computed(() => {
  if (props.warningCount !== undefined) return props.warningCount
  return props.hasNewWarning ? 1 : 0
})

const currentRole = computed(() => props.currentRole || 'user')

// 用户名首字母(取前2字符,用于文字头像) - 零图像依赖,零性能开销
const userInitials = computed(() => {
  const name = props.userName || ''
  if (!name) return '?'
  // 中文取前1字符,英文取前2字符大写
  if (/[\u4e00-\u9fa5]/.test(name)) {
    return name.slice(-1)  // 中文取最后一个字(通常是名)
  }
  return name.slice(0, 2).toUpperCase()
})

function handleCommand(command: string) {
  switch (command) {
    case 'settings':
      emit('go-settings')
      break
    case 'theme':
      emit('toggle-theme')
      break
    case 'onboarding':
      props.onRestartOnboarding()
      break
    case 'logout':
      emit('logout')
      break
  }
}
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

/* UI 升级 v3.2: 用户信息 chip - 头像+姓名+角色 */
.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 4px 4px;
  border-radius: 18px;
  cursor: pointer;
  transition: background var(--transition-fast) var(--transition-timing);
  outline: none;
}

.user-chip:hover,
.user-chip:focus-visible {
  background: var(--bg-hover);
}

.user-chip:focus-visible {
  box-shadow: var(--ring-focus);
}

/* 文字头像 - 角色色差异化,零图像依赖 */
.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: var(--role-accent-current, var(--primary-color));
  overflow: hidden;
  text-transform: uppercase;
  flex-shrink: 0;
  transition: background var(--transition-fast) var(--transition-timing);
}

/* 角色色差异化 - 保持品牌主色不变,仅头像背景差异 */
.user-avatar[data-role='user'] {
  background: linear-gradient(135deg, #7ab0a8, #5a8e87);
}

.user-avatar[data-role='counselor'] {
  background: linear-gradient(135deg, var(--primary-500), var(--primary-600));
}

.user-avatar[data-role='admin'] {
  background: linear-gradient(135deg, #6b7280, #4a5260);
}

.user-meta {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
  min-width: 0;
}

.user-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-role {
  font-size: 10px;
  color: var(--text-secondary);
}

.user-caret {
  font-size: 10px;
  color: var(--text-secondary);
  transition: transform var(--transition-fast) var(--transition-timing);
}

/* 下拉打开时箭头旋转 - 通过 :focus-within 检测 */
.user-chip:focus-within .user-caret {
  transform: rotate(180deg);
}

/* 响应式：移动端头部紧凑布局 */
@media (max-width: 768px) {
  /* VIS-015 修复：移动端显示汉堡菜单按钮 */
  .mobile-menu-btn {
    display: inline-flex;
  }

  /* 移动端头部右侧紧凑布局 */
  .header-right {
    gap: var(--spacing-sm);
  }

  /* 移动端隐藏用户名/角色,仅保留头像 */
  .user-meta {
    display: none;
  }

  .user-caret {
    display: none;
  }

  .user-chip {
    padding: 0;
  }
}

/* 减少动效偏好 */
@media (prefers-reduced-motion: reduce) {
  .user-chip,
  .user-avatar,
  .user-caret {
    transition: none;
  }
}
</style>

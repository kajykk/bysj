<template>
  <SkipLink />
  <el-container class="layout-root">
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
          v-for="section in groupedMenus"
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
            <el-menu-item :index="item.path">
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

    <el-container>
      <el-header class="layout-header">
        <div class="header-left">
          <!-- VIS-015 修复：移动端汉堡菜单按钮，用于展开被收起的侧边栏 -->
          <el-button
            class="mobile-menu-btn"
            :aria-label="t('layout.expand')"
            circle
            size="small"
            @click="layout.toggleSidebar"
          >
            <el-icon><Menu /></el-icon>
          </el-button>
          <BreadcrumbNav />
        </div>
        <div class="header-right">
          <el-badge
            :is-dot="hasNewWarning"
            class="warning-badge"
            @click="goWarnings"
          >
            <el-button
              size="small"
              :icon="BellIcon"
              circle
              :aria-label="hasNewWarning ? t('layout.newWarning') : t('layout.noWarning')"
            />
          </el-badge>
          <HelpCenter :on-restart-onboarding="restartOnboarding" />
          <el-tag>{{ roleLabel }}</el-tag>
          <span>{{ auth.user?.nickname || auth.user?.username }}</span>
          <el-button
            size="small"
            @click="handleLogout"
          >
            {{ t('layout.logout') }}
          </el-button>
        </div>
      </el-header>
      <el-main
        id="main-content"
        class="layout-main"
        tabindex="-1"
      >
        <router-view v-slot="{ Component: RouteComponent }">
          <transition
            name="fade-slide"
            mode="out-in"
          >
            <keep-alive :include="cachedComponentNames">
              <component :is="RouteComponent" />
            </keep-alive>
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
  <!-- I1 改进：异步任务进度反馈浮层 -->
  <TaskProgressNotification />
  <!-- I2 改进：新手引导系统 -->
  <OnboardingTour :role="auth.role" />
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElNotification } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { Bell, Fold, Expand, HomeFilled, Warning, User, Setting, Document, DataLine, ChatLineRound, Calendar, Reading, BellFilled, Monitor, Promotion, Menu } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useLayoutStore } from '@/stores/layout'
import { wsClient, useWebSocket } from '@/composables/useWebSocket'
import { useOnboarding } from '@/composables/useOnboarding'
import BreadcrumbNav from '@/components/common/BreadcrumbNav.vue'
import SkipLink from '@/components/common/SkipLink.vue'
import TaskProgressNotification from '@/components/common/TaskProgressNotification.vue'
import OnboardingTour from '@/components/common/OnboardingTour.vue'
import HelpCenter from '@/components/common/HelpCenter.vue'

const BellIcon = Bell
const { t } = useI18n()

// 性能优化：keep-alive 缓存设置页等不需要实时数据的页面，避免重复渲染
const cachedComponentNames = ['UserSettingsPage', 'CounselorSettingsPage', 'AdminSettingsPage']

// L-26 修复：高风险等级集合提取为常量，避免每次消息处理时重新创建数组
const HIGH_RISK_LEVELS = new Set(['high', 'critical', '3', '4'])

// ISS-i18n: 风险等级标签改用 i18n 翻译，支持多语言切换
const WARNING_LEVEL_KEY_MAP: Record<string, string> = {
  none: 'warning.riskLevelNone',
  low: 'warning.riskLevelLow',
  medium: 'warning.riskLevelMedium',
  high: 'warning.riskLevelHigh',
  critical: 'warning.riskLevelCritical',
  '0': 'warning.riskLevelNone',
  '1': 'warning.riskLevelLow',
  '2': 'warning.riskLevelMedium',
  '3': 'warning.riskLevelHigh',
  '4': 'warning.riskLevelCritical',
}

interface MenuItem {
  titleKey: string
  path: string
  icon?: Component
  tourTarget?: string
}

interface MenuSection {
  key: string
  labelKey: string
  first?: MenuItem
  items: MenuItem[]
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const layout = useLayoutStore()
const { hasNewWarning, incrementUnread, resetUnread } = useWebSocket()

const roleMenus: Record<string, MenuItem[]> = {
  user: [
    { titleKey: 'nav.user.home', path: '/user/dashboard', icon: HomeFilled, tourTarget: 'user-dashboard' },
    { titleKey: 'nav.user.risk', path: '/user/risk', icon: DataLine, tourTarget: 'user-risk' },
    { titleKey: 'nav.user.modelTraining', path: '/user/model-training', icon: Document },
    { titleKey: 'nav.user.intervention', path: '/user/intervention', icon: Calendar },
    { titleKey: 'nav.user.content', path: '/user/content', icon: Reading },
    { titleKey: 'nav.user.warnings', path: '/user/warnings', icon: Warning, tourTarget: 'user-warnings' },
    { titleKey: 'nav.user.assessments', path: '/user/assessments', icon: ChatLineRound },
    { titleKey: 'nav.user.settings', path: '/user/settings', icon: Setting },
    { titleKey: 'nav.user.reports', path: '/user/reports', icon: Document }
  ],
  counselor: [
    { titleKey: 'nav.counselor.home', path: '/counselor/dashboard', icon: HomeFilled },
    { titleKey: 'nav.counselor.warnings', path: '/counselor/warnings', icon: Warning, tourTarget: 'counselor-warnings' },
    { titleKey: 'nav.counselor.users', path: '/counselor/users', icon: User, tourTarget: 'counselor-users' },
    { titleKey: 'nav.counselor.reviews', path: '/counselor/reviews', icon: ChatLineRound },
    { titleKey: 'nav.counselor.settings', path: '/counselor/settings', icon: Setting }
  ],
  admin: [
    { titleKey: 'nav.admin.home', path: '/admin/dashboard', icon: HomeFilled, tourTarget: 'admin-dashboard' },
    { titleKey: 'nav.admin.templates', path: '/admin/templates', icon: Document },
    { titleKey: 'nav.admin.settings', path: '/admin/settings', icon: Setting },
    { titleKey: 'nav.admin.operationLogs', path: '/admin/operation-logs', icon: Reading },
    { titleKey: 'nav.admin.alerts', path: '/admin/alerts', icon: BellFilled },
    { titleKey: 'nav.admin.silences', path: '/admin/silences', icon: Bell },
    { titleKey: 'nav.admin.crisisEvents', path: '/admin/crisis-events', icon: Warning },
    { titleKey: 'nav.admin.reports', path: '/admin/reports', icon: Document },
    { titleKey: 'nav.admin.observability', path: '/admin/observability', icon: DataLine, tourTarget: 'admin-observability' },
    { titleKey: 'nav.admin.monitoring', path: '/admin/monitoring', icon: Monitor },
    { titleKey: 'nav.admin.canary', path: '/admin/canary', icon: Promotion }
  ]
}

const menus = computed(() => roleMenus[auth.role] || [])
const groupedMenus = computed<MenuSection[]>(() => {
  const items = menus.value
  if (!items.length) return []
  const dashboard = items.find((item) => item.path.endsWith('/dashboard'))
  const daily = items.filter((item) => /risk|warning|users|intervention|content|template|assessment|report|monitoring|observability/.test(item.path))
  const settings = items.filter((item) => item.path.includes('settings') || item.path.includes('operation-logs') || item.path.includes('canary'))
  const remainder = items.filter((item) => !daily.includes(item) && !settings.includes(item) && item !== dashboard)
  return [
    { key: 'daily', labelKey: 'nav.sectionDaily', first: dashboard, items: dashboard ? [dashboard, ...daily.filter((item) => item !== dashboard)] : daily },
    { key: 'review', labelKey: 'nav.sectionReview', items: remainder.filter((item) => item.path.includes('reports') || item.path.includes('reviews') || item.path.includes('assessments')) },
    { key: 'settings', labelKey: 'nav.sectionSettings', items: settings },
  ].filter((section) => section.items.length > 0)
})
const activePath = computed(() => route.path)
const asideWidth = computed(() => layout.sidebarCollapsed ? '64px' : '220px')

// I2 改进：新手引导系统
const { tryStartOnboarding, restartTour } = useOnboarding(auth.role)

const roleLabel = computed(() => {
  if (auth.role === 'admin') return t('role.admin')
  if (auth.role === 'counselor') return t('role.counselor')
  return t('role.user')
})

const goWarnings = () => {
  resetUnread()
  const path = auth.role === 'counselor' ? '/counselor/warnings' : '/user/warnings'
  router.push(path)
}

// I2 改进：重启新手引导
const restartOnboarding = () => {
  restartTour()
}

// VIS-015 修复：移动端路由变化时自动收起侧边栏，避免遮挡内容
const isMobile = () => window.matchMedia('(max-width: 768px)').matches

watch(
  () => route.path,
  () => {
    if (isMobile() && !layout.sidebarCollapsed) {
      layout.setSidebarCollapsed(true)
    }
  }
)

let removeWsListener: (() => void) | null = null

const bindWebSocket = () => {
  removeWsListener?.()
  const userId = auth.user?.id
  if (!userId || !auth.token) {
    wsClient.disconnect()
    return
  }

  wsClient.rebindSession(userId, auth.token)
  removeWsListener = wsClient.onMessage((msg) => {
    incrementUnread()
    const rawLevel = String(msg.data.risk_level ?? '')
    const levelKey = WARNING_LEVEL_KEY_MAP[rawLevel]
    const level = levelKey ? t(levelKey) : rawLevel
    const isHighRisk = HIGH_RISK_LEVELS.has(rawLevel)
    // M-FE-5 修复：通知文案改用 i18n t() 函数，支持多语言
    ElNotification({
      title: t('layout.warningNotificationTitle'),
      message: t('layout.warningNotificationMessage', { level }),
      type: isHighRisk ? 'error' : 'warning',
      duration: 8000,
    })
  })
}

onMounted(() => {
  bindWebSocket()
  // VIS-015 修复：移动端首次加载时自动收起侧边栏，避免遮挡内容
  if (isMobile() && !layout.sidebarCollapsed) {
    layout.setSidebarCollapsed(true)
  }
  // I2 改进：首次登录自动启动新手引导 (延迟 500ms 等 DOM 渲染完成)
  setTimeout(() => {
    tryStartOnboarding()
  }, 500)
})

watch(
  () => [auth.user?.id, auth.token],
  () => {
    bindWebSocket()
  },
  { immediate: false }
)

onUnmounted(() => {
  wsClient.disconnect()
  removeWsListener?.()
})

const handleLogout = async () => {
  try {
    await ElMessageBox.confirm(t('layout.logoutConfirm'), t('layout.logoutConfirmTitle'), { type: 'warning' })
  } catch {
    return
  }
  wsClient.disconnect()
  await auth.logout()
  await router.push('/login')
}
</script>

<style scoped>
.layout-root {
  min-height: 100dvh;
}

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

/* VIS-015 修复：侧边栏遮罩层 - 桌面端隐藏，移动端显示 */
.sidebar-backdrop {
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

.layout-main {
  background: var(--bg-page);
  position: relative;
}

.layout-main::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--gradient-surface);
  pointer-events: none;
  z-index: 0;
}

.layout-main > * {
  position: relative;
  z-index: 1;
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

  /* VIS-015 修复：移动端显示汉堡菜单按钮 */
  .mobile-menu-btn {
    display: inline-flex;
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

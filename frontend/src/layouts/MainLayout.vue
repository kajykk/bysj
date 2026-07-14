<template>
  <SkipLink />
  <el-container class="layout-root">
    <SidebarMenu
      :active-path="activePath"
      :menus="groupedMenus"
    />

    <el-container>
      <LayoutHeader
        :role-label="roleLabel"
        :has-new-warning="hasNewWarning"
        :user-name="auth.user?.nickname || auth.user?.username || ''"
        :on-restart-onboarding="restartOnboarding"
        @go-warnings="goWarnings"
        @logout="handleLogout"
        @toggle-sidebar="layout.toggleSidebar"
      />
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
import { onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElNotification } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useLayoutStore } from '@/stores/layout'
import { wsClient, useWebSocket } from '@/composables/useWebSocket'
import { useOnboarding } from '@/composables/useOnboarding'
import SkipLink from '@/components/common/SkipLink.vue'
import TaskProgressNotification from '@/components/common/TaskProgressNotification.vue'
import OnboardingTour from '@/components/common/OnboardingTour.vue'
import SidebarMenu from './components/main-layout/SidebarMenu.vue'
import LayoutHeader from './components/main-layout/LayoutHeader.vue'
import { useLayoutMenu } from './components/main-layout/useLayoutMenu'

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

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const layout = useLayoutStore()
const { hasNewWarning, incrementUnread, resetUnread } = useWebSocket()

const { groupedMenus, activePath, roleLabel } = useLayoutMenu()

// I2 改进：新手引导系统
const { tryStartOnboarding, restartTour } = useOnboarding(auth.role)

// I2 改进：重启新手引导
const restartOnboarding = () => {
  restartTour()
}

const goWarnings = () => {
  resetUnread()
  const path = auth.role === 'counselor' ? '/counselor/warnings' : '/user/warnings'
  router.push(path)
}

// VIS-015 修复：移动端路由变化时自动收起侧边栏，避免遮挡内容
const isMobile = () => window.matchMedia('(max-width: 768px)').matches

watch(
  () => route.path,
  () => {
    if (isMobile() && !layout.sidebarCollapsed) {
      layout.setSidebarCollapsed(true)
    }
    // P1-4 无障碍：路由变化时将焦点恢复到主内容区，便于键盘/读屏用户立即定位新页面内容
    nextTick(() => {
      const mainContent = document.getElementById('main-content')
      if (mainContent) {
        mainContent.focus()
      }
    })
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
</style>

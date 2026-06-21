<template>
  <SkipLink />
  <el-container class="layout-root">
    <el-aside
      :width="asideWidth"
      class="layout-aside"
      :class="{ collapsed: layout.sidebarCollapsed }"
    >
      <div class="logo">
        <span v-if="!layout.sidebarCollapsed">心理预警平台</span>
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
        <el-tooltip
          v-for="item in menus"
          :key="item.path"
          :content="item.title"
          :disabled="!layout.sidebarCollapsed"
          placement="right"
        >
          <el-menu-item :index="item.path">
            <el-icon v-if="item.icon">
              <component :is="item.icon" />
            </el-icon>
            <template #title>
              {{ item.title }}
            </template>
          </el-menu-item>
        </el-tooltip>
      </el-menu>
      <div
        class="collapse-btn"
        @click="layout.toggleSidebar"
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
        v1.28-final
      </div>
    </el-aside>

    <el-container>
      <el-header class="layout-header">
        <div class="header-left">
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
            />
          </el-badge>
          <el-tag>{{ roleLabel }}</el-tag>
          <span>{{ auth.user?.nickname || auth.user?.username }}</span>
          <el-button
            size="small"
            @click="handleLogout"
          >
            退出
          </el-button>
        </div>
      </el-header>
      <el-main
        id="main-content"
        class="layout-main"
        tabindex="-1"
      >
        <router-view v-slot="{ Component }">
          <transition
            name="fade-slide"
            mode="out-in"
          >
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElNotification } from 'element-plus'
import { Bell, Fold, Expand, HomeFilled, Warning, User, Setting, Document, DataLine, ChatLineRound, Calendar, Reading } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useLayoutStore } from '@/stores/layout'
import { wsClient, useWebSocket } from '@/composables/useWebSocket'
import BreadcrumbNav from '@/components/common/BreadcrumbNav.vue'
import SkipLink from '@/components/common/SkipLink.vue'

const BellIcon = Bell

interface MenuItem {
  title: string
  path: string
  icon?: Component
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const layout = useLayoutStore()
const { hasNewWarning, incrementUnread, resetUnread } = useWebSocket()

const roleMenus: Record<string, MenuItem[]> = {
  user: [
    { title: '用户首页', path: '/user/dashboard', icon: HomeFilled },
    { title: '风险评估', path: '/user/risk', icon: DataLine },
    { title: '模型训练入口', path: '/user/model-training', icon: Document },
    { title: '干预计划', path: '/user/intervention', icon: Calendar },
    { title: '内容中心', path: '/user/content', icon: Reading },
    { title: '我的预警', path: '/user/warnings', icon: Warning },
    { title: '评估记录', path: '/user/assessments', icon: ChatLineRound },
    { title: '个人设置', path: '/user/settings', icon: Setting }
  ],
  counselor: [
    { title: '咨询师首页', path: '/counselor/dashboard', icon: HomeFilled },
    { title: '预警处理', path: '/counselor/warnings', icon: Warning },
    { title: '用户管理', path: '/counselor/users', icon: User },
    { title: '个人设置', path: '/counselor/settings', icon: Setting }
  ],
  admin: [
    { title: '管理员首页', path: '/admin/dashboard', icon: HomeFilled },
    { title: '模板管理', path: '/admin/templates', icon: Document },
    { title: '系统设置', path: '/admin/settings', icon: Setting },
    { title: '操作日志', path: '/admin/operation-logs', icon: Reading }
  ]
}

const menus = computed(() => roleMenus[auth.role] || [])
const activePath = computed(() => route.path)
const asideWidth = computed(() => layout.sidebarCollapsed ? '64px' : '220px')

const roleLabel = computed(() => {
  if (auth.role === 'admin') return '管理员'
  if (auth.role === 'counselor') return '咨询师'
  return '普通用户'
})

const goWarnings = () => {
  resetUnread()
  const path = auth.role === 'counselor' ? '/counselor/warnings' : '/user/warnings'
  router.push(path)
}

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
    const levelMap: Record<string, string> = { none: '无', low: '低', medium: '中', high: '高', critical: '严重', '0': '无', '1': '低', '2': '中', '3': '高', '4': '严重' }
    const rawLevel = String(msg.data.risk_level ?? '')
    const level = levelMap[rawLevel] || rawLevel
    const isHighRisk = ['high', 'critical', '3', '4'].includes(rawLevel)
    ElNotification({
      title: '风险预警通知',
      message: `检测到${level}风险等级预警，请及时查看`,
      type: isHighRisk ? 'error' : 'warning',
      duration: 8000,
    })
  })
}

onMounted(() => {
  bindWebSocket()
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
    await ElMessageBox.confirm('确认退出登录吗？', '提示', { type: 'warning' })
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
  min-height: 100vh;
}

.layout-aside {
  border-right: 1px solid #ebeef5;
  background: #fff;
  transition: width 0.3s ease;
  position: relative;
}

.layout-aside.collapsed .logo {
  padding: 0;
}

.logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  border-bottom: 1px solid #f0f2f5;
  overflow: hidden;
  white-space: nowrap;
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
  border-top: 1px solid #ebeef5;
  background: #fff;
  transition: background 0.3s;
}

.collapse-btn:hover {
  background: #f5f7fa;
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
  font-size: 11px;
  color: #909399;
  border-top: 1px solid #ebeef5;
}

.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #ebeef5;
  background: #fff;
}

.header-left {
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.warning-badge {
  cursor: pointer;
}

.layout-main {
  background: #f5f7fa;
}
</style>

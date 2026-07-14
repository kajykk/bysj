/**
 * MainLayout 菜单数据 composable。
 * 从原 MainLayout.vue 提取菜单配置、分组计算与角色标签逻辑，保持行为一致。
 */
import { computed, type Component } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  Bell,
  HomeFilled,
  Warning,
  User,
  Setting,
  Document,
  DataLine,
  ChatLineRound,
  Calendar,
  Reading,
  BellFilled,
  Monitor,
  Promotion,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

export interface MenuItem {
  titleKey: string
  path: string
  icon?: Component
  tourTarget?: string
}

export interface MenuSection {
  key: string
  labelKey: string
  first?: MenuItem
  items: MenuItem[]
}

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

export function useLayoutMenu() {
  const { t } = useI18n()
  const route = useRoute()
  const auth = useAuthStore()

  const menus = computed(() => roleMenus[auth.role] || [])

  const groupedMenus = computed<MenuSection[]>(() => {
    const items = menus.value
    if (!items.length) return []
    const dashboard = items.find((item) => item.path.endsWith('/dashboard'))
    const dailyItems = items.filter((item) => /risk|warning|users|intervention|content/.test(item.path))
    const reviewItems = items.filter((item) => /assessment|report/.test(item.path))
    const settingsItems = items.filter((item) => item.path.includes('settings') || item.path.includes('operation-logs'))
    const opsItems = items.filter((item) => /monitoring|observability|canary|alerts|silences|crisis-events/.test(item.path))
    return [
      { key: 'daily', labelKey: 'nav.sectionDaily', first: dashboard, items: dashboard ? [dashboard, ...dailyItems.filter((item) => item !== dashboard)] : dailyItems },
      { key: 'review', labelKey: 'nav.sectionReview', items: reviewItems },
      { key: 'ops', labelKey: 'nav.sectionOps', items: opsItems },
      { key: 'settings', labelKey: 'nav.sectionSettings', items: settingsItems },
    ].filter((section) => section.items.length > 0)
  })

  const activePath = computed(() => route.path)

  const roleLabel = computed(() => {
    if (auth.role === 'admin') return t('role.admin')
    if (auth.role === 'counselor') return t('role.counselor')
    return t('role.user')
  })

  return {
    groupedMenus,
    activePath,
    roleLabel,
  }
}

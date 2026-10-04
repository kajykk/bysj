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
  Monitor,
  Promotion,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

export interface MenuItem {
  titleKey: string
  path: string
  icon?: Component
  tourTarget?: string
  /** UI 升级 v3.2: 未读数徽章 - 大于 0 时显示 */
  badge?: number
  /** 徽章配色变体: danger(默认,预警) / warning(待办) / primary(信息) */
  badgeVariant?: 'danger' | 'warning' | 'primary'
}

export interface MenuSection {
  key: string
  labelKey: string
  first?: MenuItem
  items: MenuItem[]
}

const adminMenus: MenuItem[] = [
  { titleKey: 'nav.admin.home', path: '/admin/dashboard', icon: HomeFilled, tourTarget: 'admin-dashboard' },
  { titleKey: 'nav.admin.templates', path: '/admin/templates', icon: Document },
  { titleKey: 'nav.admin.settings', path: '/admin/settings', icon: Setting },
  { titleKey: 'nav.admin.operationLogs', path: '/admin/operation-logs', icon: Reading },
  // AUDIT-2026-10-01 (P2)：合规审计日志（GDPR/等保场景专用查询视图）
  { titleKey: 'nav.admin.auditLogs', path: '/admin/audit-logs', icon: Reading },
  { titleKey: 'nav.admin.alerts', path: '/admin/alerts', icon: Bell },
  { titleKey: 'nav.admin.silences', path: '/admin/silences', icon: Bell },
  { titleKey: 'nav.admin.crisisEvents', path: '/admin/crisis-events', icon: Warning },
  // AUDIT-2026-10-01：复核任务的「指定分配」入口。路径复用 counselor 页面
  // （该路由的 meta.role 已放开给 admin/super_admin），管理员据此把任务分给具体咨询师。
  { titleKey: 'nav.admin.reviews', path: '/counselor/reviews', icon: ChatLineRound },
  { titleKey: 'nav.admin.reports', path: '/admin/reports', icon: Document },
  { titleKey: 'nav.admin.observability', path: '/admin/observability', icon: DataLine, tourTarget: 'admin-observability' },
  { titleKey: 'nav.admin.monitoring', path: '/admin/monitoring', icon: Monitor },
  { titleKey: 'nav.admin.canary', path: '/admin/canary', icon: Promotion },
  // AUDIT-2026-10-01 (P1-7)：模型暂停开关（事故止血）。此前无 UI 入口。
  { titleKey: 'nav.admin.modelKillSwitch', path: '/admin/model-kill-switch', icon: Warning }
]

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
  admin: adminMenus,
  // 平台管理员 (super_admin): 与 admin 共用平台级菜单
  super_admin: adminMenus
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
    // AUDIT-2026-10-01：正则补上 `review`。原为 /assessment|report/，
    // 导致 `/counselor/reviews`（咨询师与管理员共用的复核任务页）落不进任何分组而被侧边栏隐藏
    // —— 实测：修复前 counselor 侧边栏只有 4 项、admin 只有 10 项，均不含该页。
    const reviewItems = items.filter((item) => /assessment|report|review/.test(item.path))
    // AUDIT-2026-10-01 (P2)：audit-logs 与 operation-logs 同族，归入同一分组
    // （即使漏配也有兜底分组兜住，这里显式归属是为了与操作日志并列展示）
    const settingsItems = items.filter((item) => item.path.includes('settings') || item.path.includes('operation-logs') || item.path.includes('audit-logs'))
    // AUDIT-2026-10-01：正则补上 `kill-switch`。这是同一类 bug 的第二次出现——
    // 不匹配任何正则的菜单项**不会渲染**，`/admin/model-kill-switch` 会被静默隐藏
    // （事故时管理员找不到止血入口）。两处修复一并记在 useLayoutMenu.test.ts 里。
    const opsItems = items.filter(
      (item) =>
        /monitoring|observability|canary|alerts|silences|crisis-events|kill-switch/.test(item.path)
    )
    const base = [
      { key: 'daily', labelKey: 'nav.sectionDaily', first: dashboard, items: dashboard ? [dashboard, ...dailyItems.filter((item) => item !== dashboard)] : dailyItems },
      { key: 'review', labelKey: 'nav.sectionReview', items: reviewItems },
      { key: 'ops', labelKey: 'nav.sectionOps', items: opsItems },
      { key: 'settings', labelKey: 'nav.sectionSettings', items: settingsItems },
    ] as MenuSection[]

    // AUDIT-2026-10-01：兜底分组。
    // 未命中任何正则的菜单项**原本不会渲染**——这个坑已经踩了三次
    // （/counselor/reviews、/admin/templates、/user/model-training 都被静默隐藏，
    //  /admin/model-kill-switch 若不处理就是第四次）。逐词往正则里补是打不完的补丁，
    // 正确的做法是让「未分组」也有归宿：新增菜单即使忘了配正则，也不会凭空消失。
    const assigned = new Set<MenuItem>(base.flatMap((section) => section.items))
    const leftover = items.filter((item) => !assigned.has(item))
    if (leftover.length) {
      base.push({ key: 'other', labelKey: 'nav.sectionOther', items: leftover })
    }
    return base.filter((section) => section.items.length > 0)
  })

  const activePath = computed(() => route.path)

  const roleLabel = computed(() => {
    if (auth.role === 'super_admin') return t('role.superAdmin')
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

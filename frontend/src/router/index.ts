import { createRouter, createWebHistory } from 'vue-router'
// R-003 修复：基础文件 (路由守卫层) 显式导入 ElMessage，避免依赖 unplugin-auto-import
// 隐式注入导致测试环境需 globalThis hack、生产环境配置失效时静默失败的可靠性问题。
// 页面/组件层仍可使用 auto-import，仅基础文件强制显式导入以保障运行时确定性。
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { resolveGuardResult, type GuardRouteMeta } from '@/router/guard'
import { ROUTE_PERMISSIONS } from '@/config/routeAccess'
import { resetUnauthorizedRedirecting } from '@/api/request'
import i18n from '@/i18n'

// H-FE-1 修复：使用顶部进度条替代全屏 loading，避免路由切换时锁定整个 UI
// 原实现调用 loadingStore.startLoading() 触发 App.vue 的 v-loading.fullscreen.lock，
// 每次路由切换都会全屏遮罩阻塞用户操作
let progressBar: HTMLDivElement | null = null
let progressTimer: ReturnType<typeof setInterval> | null = null

function ensureProgressBar(): HTMLDivElement {
  if (progressBar && document.body.contains(progressBar)) return progressBar
  const bar = document.createElement('div')
  bar.style.cssText = [
    'position: fixed',
    'top: 0',
    'left: 0',
    'height: 3px',
    'width: 0%',
    'background: #409eff',
    'z-index: 9999',
    'transition: width 0.2s ease, opacity 0.3s ease',
    'pointer-events: none',
    'opacity: 0',
  ].join(';')
  document.body.appendChild(bar)
  progressBar = bar
  return bar
}

function startProgress() {
  const bar = ensureProgressBar()
  bar.style.opacity = '1'
  bar.style.width = '0%'
  if (progressTimer) clearInterval(progressTimer)
  let width = 0
  // 模拟进度增长，越接近 90% 越慢，但不达到 100%（等待 afterEach 完成）
  progressTimer = setInterval(() => {
    width += (90 - width) * 0.1
    bar.style.width = `${width}%`
  }, 200)
}

function stopProgress() {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
  if (progressBar) {
    progressBar.style.width = '100%'
    const bar = progressBar
    setTimeout(() => {
      bar.style.opacity = '0'
    }, 200)
  }
}

// L-FE-19 修复：移除 webpackChunkName 注释（对 Vite 无效，Vite 通过 manualChunks 配置分包）
const routes = [
  { path: '/login', component: () => import('@/views/login/LoginPage.vue') },
  { path: '/reset-password', component: () => import('@/views/login/ResetPasswordPage.vue') },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      // User routes - lazy loaded
      { path: 'user/dashboard', alias: '/user/dashboard', component: () => import('@/views/user/UserDashboard.vue'), meta: { role: 'user', title: 'nav.user.home' } },
      { path: 'user/risk', alias: ['/user/risk', '/user/risk-report'], component: () => import('@/views/user/UserRiskPage.vue'), meta: { role: 'user', title: 'nav.user.risk' } },
      { path: 'user/model-training', alias: '/user/model-training', component: () => import('@/views/user/UserModelTrainingPage.vue'), meta: { role: 'user', title: 'nav.user.modelTraining' } },
      { path: 'user/intervention', alias: '/user/intervention', component: () => import('@/views/user/UserInterventionPage.vue'), meta: { role: 'user', title: 'nav.user.intervention' } },
      { path: 'user/content', alias: ['/user/content', '/user/education'], component: () => import('@/views/user/UserContentPage.vue'), meta: { role: 'user', title: 'nav.user.content' } },
      { path: 'user/settings', alias: '/user/profile', component: () => import('@/views/user/UserSettingsPage.vue'), meta: { role: 'user', title: 'nav.user.settings', keepAlive: true } },
      {
        path: 'user/warnings',
        alias: '/user/warnings',
        component: () => import('@/views/user/UserWarningsPage.vue'),
        meta: { role: 'user', permissions: ROUTE_PERMISSIONS.userWarnings }
      },
      {
        path: 'user/assessments',
        alias: ['/user/assessments', '/user/history'],
        component: () => import('@/views/user/UserAssessmentsPage.vue'),
        meta: { role: 'user', permissions: ROUTE_PERMISSIONS.userAssessments }
      },
      {
        path: 'user/assessments/:id',
        alias: '/user/education/:id',
        component: () => import('@/views/user/UserAssessmentDetailPage.vue'),
        meta: { role: 'user', permissions: ROUTE_PERMISSIONS.userAssessments }
      },
      // Counselor routes - lazy loaded
      { path: 'counselor/dashboard', alias: '/counselor/dashboard', component: () => import('@/views/counselor/CounselorDashboard.vue'), meta: { role: 'counselor', title: 'nav.counselor.home' } },
      {
        path: 'counselor/warnings',
        alias: '/counselor/alerts',
        component: () => import('@/views/counselor/CounselorWarningsPage.vue'),
        meta: {
          role: 'counselor',
          permissions: ROUTE_PERMISSIONS.counselorWarnings
        }
      },
      {
        path: 'counselor/users',
        alias: '/counselor/clients',
        component: () => import('@/views/counselor/CounselorUsersPage.vue'),
        meta: { role: 'counselor', permissions: ROUTE_PERMISSIONS.counselorConsultation }
      },
      {
        path: 'counselor/users/:id',
        alias: '/counselor/clients/:id',
        component: () => import('@/views/counselor/CounselorUserDetailPage.vue'),
        meta: { role: 'counselor', permissions: ROUTE_PERMISSIONS.counselorConsultation }
      },
      { path: 'counselor/settings', alias: '/counselor/settings', component: () => import('@/views/counselor/CounselorSettingsPage.vue'), meta: { role: 'counselor', title: 'nav.counselor.settings', keepAlive: true } },
      {
        path: 'counselor/reviews',
        alias: '/counselor/reviews',
        component: () => import('@/views/counselor/CounselorReviewListPage.vue'),
        meta: { role: 'counselor', permissions: ROUTE_PERMISSIONS.counselorReviews, title: 'nav.counselor.reviews' }
      },
      {
        path: 'counselor/reviews/:id',
        alias: '/counselor/reviews/:id',
        component: () => import('@/views/counselor/CounselorReviewDetailPage.vue'),
        meta: { role: 'counselor', permissions: ROUTE_PERMISSIONS.counselorReviews, title: 'nav.counselor.reviewDetail' }
      },
      // Admin routes - lazy loaded
      { path: 'admin/dashboard', alias: '/admin/dashboard', component: () => import('@/views/admin/AdminDashboard.vue'), meta: { role: 'admin', title: 'nav.admin.home' } },
      { path: 'admin/templates', alias: ['/admin/templates', '/admin/intervention-library'], component: () => import('@/views/admin/AdminTemplatesPage.vue'), meta: { role: 'admin', title: 'nav.admin.templates' } },
      { path: 'admin/settings', alias: '/admin/settings', component: () => import('@/views/admin/AdminSettingsPage.vue'), meta: { role: 'admin', title: 'nav.admin.settings', keepAlive: true } },
      {
        path: 'admin/operation-logs',
        alias: '/admin/logs',
        component: () => import('@/views/admin/AdminOperationLogsPage.vue'),
        meta: { role: 'admin', permissions: ROUTE_PERMISSIONS.adminOperationLogs, title: 'nav.admin.operationLogs' }
      },
      {
        path: 'admin/crisis-events',
        alias: '/admin/crisis-events',
        component: () => import('@/views/admin/AdminCrisisEventsPage.vue'),
        meta: { role: 'admin', title: 'nav.admin.crisisEvents' }
      },
      {
        path: 'admin/alerts',
        alias: '/admin/alerts',
        component: () => import('@/views/admin/AdminAlertsPage.vue'),
        meta: { role: 'admin', permissions: ROUTE_PERMISSIONS.adminAlerts, title: 'nav.admin.alerts' }
      },
      {
        path: 'admin/silences',
        alias: '/admin/silences',
        component: () => import('@/views/admin/AdminSilencesPage.vue'),
        meta: { role: 'admin', permissions: ROUTE_PERMISSIONS.adminSilences, title: 'nav.admin.silences' }
      },
      {
        path: 'user/reports',
        alias: '/user/reports',
        component: () => import('@/views/user/UserReportsPage.vue'),
        meta: { role: 'user', permissions: ROUTE_PERMISSIONS.userReports, title: 'nav.user.reports' }
      },
      {
        path: 'admin/reports',
        alias: '/admin/reports',
        component: () => import('@/views/admin/AdminReportsPage.vue'),
        meta: { role: 'admin', permissions: ROUTE_PERMISSIONS.adminReports, title: 'nav.admin.reports' }
      },
      {
        path: 'admin/observability',
        alias: '/admin/observability',
        component: () => import('@/views/admin/AdminObservabilityPage.vue'),
        meta: { role: 'admin', permissions: ROUTE_PERMISSIONS.adminObservability, title: 'nav.admin.observability' }
      },
      {
        path: 'admin/monitoring',
        alias: '/admin/monitoring',
        component: () => import('@/views/admin/AdminMonitoringPage.vue'),
        meta: { role: 'admin', permissions: ROUTE_PERMISSIONS.adminMonitoring, title: 'nav.admin.monitoring' }
      },
      {
        path: 'admin/canary',
        alias: '/admin/canary',
        component: () => import('@/views/admin/AdminCanaryPage.vue'),
        meta: { role: 'admin', permissions: ROUTE_PERMISSIONS.adminCanary, title: 'nav.admin.canary' }
      },
      // Common routes
      { path: 'forbidden', alias: '/403', component: () => import('@/views/common/ForbiddenPage.vue') }
    ]
  },
  // L-FE-5 修复：catch-all 路由渲染 404 页面，而非重定向到 /login（避免未知 URL 被静默吞掉）
  { path: '/:pathMatch(.*)*', component: () => import('@/views/common/NotFoundPage.vue') }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  // H-FE-6 修复：配置 scrollBehavior，浏览器前进/后退恢复滚动位置，新导航回到顶部
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition || { top: 0 }
  },
})

router.beforeEach((to, from) => {
  if (to.path !== from.path) {
    startProgress()
  }

  const auth = useAuthStore()

  const meta: GuardRouteMeta = {
    role: typeof to.meta.role === 'string' ? to.meta.role : undefined,
    permissions: Array.isArray(to.meta.permissions) ? to.meta.permissions : undefined
  }

  const result = resolveGuardResult(
    to.path,
    meta,
    {
      isLoggedIn: auth.isLoggedIn,
      role: auth.role
    }
  )

  if (result === true) {
    return true
  }

  const t = i18n.global.t.bind(i18n.global)

  if (result === '/forbidden' && to.path !== '/forbidden') {
    ElMessage.warning(t('router.noPermissionAccess'))
    return { path: '/forbidden' }
  }

  if (result === '/login' && to.path !== '/login') {
    ElMessage.info(t('router.pleaseLoginFirst'))
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  return result
})

router.afterEach(() => {
  stopProgress()
  // M-FE-4 修复：导航完成后复位 401 跳转标志，避免标志永久置位
  resetUnauthorizedRedirecting()
})

// 导航被取消或抛出异常时 afterEach 不会触发，需在此清理 loading 状态避免卡死
router.onError((error, to) => {
  stopProgress()
  // H-11 修复：处理 chunk 加载失败（部署后旧 chunk hash 失效）。
  // 检测 ChunkLoadError / 动态 import 失败，自动刷新页面以加载最新资源。
  // R-001 修复：收窄错误判定，移除宽泛的 SyntaxError 名称匹配，
  // 避免吞掉真实代码语法错误。仅当 SyntaxError 的 message 包含 chunk 失败特征时
  // （如服务器返回 HTML 错误页被当作 JS 解析），才视为 chunk 失效。
  const CHUNK_FAIL_PATTERN =
    /Failed to fetch dynamically imported module|Loading chunk .* failed|Importing a module script failed/i
  const isChunkLoadError =
    error?.name === 'ChunkLoadError' ||
    CHUNK_FAIL_PATTERN.test(error?.message ?? '') ||
    (error?.name === 'SyntaxError' && CHUNK_FAIL_PATTERN.test(error?.message ?? ''))
  if (isChunkLoadError) {
    // ISS-011 修复：使用 sessionStorage 记录上次刷新时间，5 秒内最多刷新 1 次。
    // 原比较逻辑 window.location.pathname !== to.fullPath 在刷新后失效，
    // 可能导致无限刷新或卡白屏。改用时间窗口限制避免循环。
    if (typeof window !== 'undefined') {
      const RELOAD_KEY = 'last_chunk_reload'
      const RELOAD_WINDOW_MS = 5000
      try {
        const lastReload = window.sessionStorage.getItem(RELOAD_KEY)
        const now = Date.now()
        if (!lastReload || now - parseInt(lastReload, 10) > RELOAD_WINDOW_MS) {
          window.sessionStorage.setItem(RELOAD_KEY, String(now))
          window.location.assign(to.fullPath)
        }
      } catch {
        // sessionStorage 不可用时静默降级，不刷新避免循环
      }
    }
  }
})

export default router

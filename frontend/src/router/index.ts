import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useLoadingStore } from '@/stores/loading'
import { resolveGuardResult, type GuardRouteMeta } from '@/router/guard'
import { ROUTE_PERMISSIONS } from '@/config/routeAccess'

const startProgress = () => {
  const loadingStore = useLoadingStore()
  loadingStore.startLoading('页面加载中...')
}

const stopProgress = () => {
  const loadingStore = useLoadingStore()
  loadingStore.stopLoading()
}

const routes = [
  { path: '/login', component: () => import('@/views/login/LoginPage.vue') },
  { path: '/reset-password', component: () => import('@/views/login/ResetPasswordPage.vue') },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      // User routes - lazy loaded
      { path: 'user/dashboard', alias: '/user/dashboard', component: () => import(/* webpackChunkName: "user-dashboard" */ '@/views/user/UserDashboard.vue'), meta: { role: 'user', title: '用户首页' } },
      { path: 'user/risk', alias: ['/user/risk', '/user/risk-report'], component: () => import(/* webpackChunkName: "user-risk" */ '@/views/user/UserRiskPage.vue'), meta: { role: 'user', title: '风险评估' } },
      { path: 'user/model-training', alias: '/user/model-training', component: () => import(/* webpackChunkName: "user-training" */ '@/views/user/UserModelTrainingPage.vue'), meta: { role: 'user', title: '模型训练' } },
      { path: 'user/intervention', alias: '/user/intervention', component: () => import(/* webpackChunkName: "user-intervention" */ '@/views/user/UserInterventionPage.vue'), meta: { role: 'user', title: '干预计划' } },
      { path: 'user/content', alias: ['/user/content', '/user/education'], component: () => import(/* webpackChunkName: "user-content" */ '@/views/user/UserContentPage.vue'), meta: { role: 'user', title: '内容中心' } },
      { path: 'user/settings', alias: '/user/profile', component: () => import(/* webpackChunkName: "user-settings" */ '@/views/user/UserSettingsPage.vue'), meta: { role: 'user', title: '个人设置' } },
      {
        path: 'user/warnings',
        alias: '/user/warnings',
        component: () => import(/* webpackChunkName: "user-warnings" */ '@/views/user/UserWarningsPage.vue'),
        meta: { role: 'user', permissions: ROUTE_PERMISSIONS.userWarnings }
      },
      {
        path: 'user/assessments',
        alias: ['/user/assessments', '/user/history'],
        component: () => import(/* webpackChunkName: "user-assessments" */ '@/views/user/UserAssessmentsPage.vue'),
        meta: { role: 'user', permissions: ROUTE_PERMISSIONS.userAssessments }
      },
      {
        path: 'user/assessments/:id',
        alias: '/user/education/:id',
        component: () => import(/* webpackChunkName: "user-assessment-detail" */ '@/views/user/UserAssessmentDetailPage.vue'),
        meta: { role: 'user', permissions: ROUTE_PERMISSIONS.userAssessments }
      },
      // Counselor routes - lazy loaded
      { path: 'counselor/dashboard', alias: '/counselor/dashboard', component: () => import(/* webpackChunkName: "counselor-dashboard" */ '@/views/counselor/CounselorDashboard.vue'), meta: { role: 'counselor', title: '咨询师首页' } },
      {
        path: 'counselor/warnings',
        alias: '/counselor/alerts',
        component: () => import(/* webpackChunkName: "counselor-warnings" */ '@/views/counselor/CounselorWarningsPage.vue'),
        meta: {
          role: 'counselor',
          permissions: ROUTE_PERMISSIONS.counselorWarnings
        }
      },
      {
        path: 'counselor/users',
        alias: '/counselor/clients',
        component: () => import(/* webpackChunkName: "counselor-users" */ '@/views/counselor/CounselorUsersPage.vue'),
        meta: { role: 'counselor', permissions: ROUTE_PERMISSIONS.counselorConsultation }
      },
      {
        path: 'counselor/users/:id',
        alias: '/counselor/clients/:id',
        component: () => import(/* webpackChunkName: "counselor-user-detail" */ '@/views/counselor/CounselorUserDetailPage.vue'),
        meta: { role: 'counselor', permissions: ROUTE_PERMISSIONS.counselorConsultation }
      },
      { path: 'counselor/settings', alias: '/counselor/settings', component: () => import(/* webpackChunkName: "counselor-settings" */ '@/views/counselor/CounselorSettingsPage.vue'), meta: { role: 'counselor', title: '个人设置' } },
      {
        path: 'counselor/reviews',
        alias: '/counselor/reviews',
        component: () => import(/* webpackChunkName: "counselor-reviews" */ '@/views/counselor/CounselorReviewListPage.vue'),
        meta: { role: 'counselor', title: '复核任务' }
      },
      {
        path: 'counselor/reviews/:id',
        alias: '/counselor/reviews/:id',
        component: () => import(/* webpackChunkName: "counselor-review-detail" */ '@/views/counselor/CounselorReviewDetailPage.vue'),
        meta: { role: 'counselor', title: '复核详情' }
      },
      // Admin routes - lazy loaded
      { path: 'admin/dashboard', alias: '/admin/dashboard', component: () => import(/* webpackChunkName: "admin-dashboard" */ '@/views/admin/AdminDashboard.vue'), meta: { role: 'admin', title: '管理员首页' } },
      { path: 'admin/templates', alias: ['/admin/templates', '/admin/intervention-library'], component: () => import(/* webpackChunkName: "admin-templates" */ '@/views/admin/AdminTemplatesPage.vue'), meta: { role: 'admin', title: '模板管理' } },
      { path: 'admin/settings', alias: '/admin/settings', component: () => import(/* webpackChunkName: "admin-settings" */ '@/views/admin/AdminSettingsPage.vue'), meta: { role: 'admin', title: '系统设置' } },
      {
        path: 'admin/operation-logs',
        alias: '/admin/logs',
        component: () => import(/* webpackChunkName: "admin-logs" */ '@/views/admin/AdminOperationLogsPage.vue'),
        meta: { role: 'admin', permissions: ROUTE_PERMISSIONS.adminOperationLogs, title: '操作日志' }
      },
      {
        path: 'admin/crisis-events',
        alias: '/admin/crisis-events',
        component: () => import(/* webpackChunkName: "admin-crisis-events" */ '@/views/admin/AdminCrisisEventsPage.vue'),
        meta: { role: 'admin', title: '危机事件' }
      },
      // Common routes
      { path: 'forbidden', alias: '/403', component: () => import('@/views/common/ForbiddenPage.vue') }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/login' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
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

  if (result === '/forbidden' && to.path !== '/forbidden') {
    ElMessage.warning('您没有权限访问该页面')
    return { path: '/forbidden' }
  }

  if (result === '/login' && to.path !== '/login') {
    ElMessage.info('请先登录')
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  return result
})

router.afterEach(() => {
  stopProgress()
})

// 导航被取消或抛出异常时 afterEach 不会触发，需在此清理 loading 状态避免卡死
router.onError(() => {
  stopProgress()
})

export default router

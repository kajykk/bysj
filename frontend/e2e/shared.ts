import { expect, type Page } from '@playwright/test'

export type RoleName = 'admin' | 'counselor' | 'user'

/** AUDIT-2026-10-01：E2E 种子口令不再硬编码在源码里（原值为公开示例口令，等同已泄露）。
 *  缺失时**立即抛错**，而不是回落到一个仓库里人尽皆知的值。
 *
 *  SEC-FIX-2026-10-05（改为惰性求值）:
 *    原实现在 `ROLE_FLOW_CONFIG` 这个**模块顶层对象字面量**里直接调用
 *    `requireEnv(...)`，于是 `import { CORS_HEADERS } from './shared'`
 *    也会在模块加载期触发三个口令校验 —— 即使该用例（如 @smoke 的
 *    auth.spec.ts，纯 mock API）根本不用口令。
 *
 *    后果：pr-quality-gates.yml 的 e2e-smoke job 只跑 mock API、不起真实
 *    后端，因此没有也不该注入种子口令；而 shared.ts 的模块级求值让它
 *    在收集阶段就抛 `缺少环境变量 E2E_ADMIN_PASSWORD`，
 *    最终表现为 `No tests found` —— 一个与被测代码完全无关的门禁失败。
 *
 *    改为惰性：口令在**实际读取时才解析**。真正跑角色登录流程的用例
 *    （role-admin / role-counselor / role-user）仍会抛错，安全加固未被削弱 ——
 *    只是不再惩罚不需要口令的 smoke 用例。
 *
 *    补充：CI 侧的正确做法是照 e2e-tests.yml 用 openssl rand 生成并写入
 *    $GITHUB_ENV；此处修复是让「不注入」成为合法状态，而非替代它。 */
function requireEnv(name: string): string {
  const value = process.env[name]
  if (!value) {
    throw new Error(
      `缺少环境变量 ${name}：E2E 种子口令不再提供默认值。请先在本机 .env（或 CI 环境）注入后再运行 E2E。`,
    )
  }
  return value
}

/** 惰性解析口令的 getter —— 模块加载时不求值，仅在实际读取时求值。 */
function lazyPassword(envName: string): string {
  let cached: string | undefined
  return () => (cached ??= requireEnv(envName))
}

export interface RoleFlowConfig {
  username: string
  /**
   * 口令 getter。调用方需 `flow.password()` 而非 `flow.password`
   * —— 改为惰性求值后，类型从 string 变为 () => string。
   * 仅 role-*.spec.ts 与 loginAsRole 使用，已同步更新。
   */
  password: () => string
  dashboardUrl: RegExp
  dashboardHeading: string
  dashboardHighlights: string[]
  secondaryRoutes: string[]
  secondaryHeadings: string[]
  tableIndexes?: number[]
  detailRoute?: string
  detailHeading?: string
}

export const ROLE_FLOW_CONFIG: Record<RoleName, RoleFlowConfig> = {
  admin: {
    username: 'admin',
    password: lazyPassword('E2E_ADMIN_PASSWORD'),
    dashboardUrl: /\/admin\/dashboard/,
    dashboardHeading: '管理员工作台',
    dashboardHighlights: ['系统状态', '管理员端'],
    secondaryRoutes: ['/admin/templates', '/admin/operation-logs'],
    secondaryHeadings: ['干预模板管理', '操作日志'],
    tableIndexes: [0, 0],
    detailRoute: undefined,
    detailHeading: undefined
  },
  counselor: {
    username: 'dr_wang',
    password: lazyPassword('E2E_COUNSELOR_PASSWORD'),
    dashboardUrl: /\/counselor\/dashboard/,
    dashboardHeading: '咨询师工作台',
    dashboardHighlights: ['今日待处理预警'],
    secondaryRoutes: ['/counselor/warnings', '/counselor/users'],
    secondaryHeadings: ['预警处理', '用户管理'],
    tableIndexes: [0, 0],
    detailRoute: '/counselor/users/1',
    detailHeading: '咨询记录'
  },
  user: {
    username: 'user_moderate',
    password: lazyPassword('E2E_USER_PASSWORD'),
    dashboardUrl: /\/user\/dashboard/,
    dashboardHeading: '用户仪表盘',
    dashboardHighlights: ['风险状态', '干预计划'],
    secondaryRoutes: ['/user/risk', '/user/intervention', '/user/warnings'],
    secondaryHeadings: ['风险评估', '当前计划', '我的预警'],
    tableIndexes: [0],
    detailRoute: undefined,
    detailHeading: undefined
  }
}

// 跨域直连后端时，route.fulfill 的响应默认不带 CORS 头，
// 浏览器会拦截伪造的 401 响应（net::ERR_FAILED），axios 收到的是 network error 而非 401，
// 导致 401 刷新拦截器不触发。所有模拟 401 的 fulfill 必须附带这些头。
export const CORS_HEADERS = {
  'access-control-allow-origin': 'http://localhost:5173',
  'access-control-allow-credentials': 'true',
  // AUDIT-2026-09-30-P1-16: 后端 CORS 白名单已补 HEAD（跨域 GDPR 探针需要）
  'access-control-allow-methods': 'GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS',
  'access-control-allow-headers': 'Authorization, Content-Type, Accept',
}

export async function loginAsRole(page: Page, role: RoleName) {
  // 跳过新手引导 Tour：el-tour 遮罩会拦截页面点击，导致测试点击超时
  await page.addInitScript(() => {
    for (const r of ['user', 'counselor', 'admin']) {
      localStorage.setItem(`dws:onboarding:completed:${r}:v1`, 'true')
    }
  })
  const credentials = ROLE_FLOW_CONFIG[role]
  await page.goto('/login')
  await page.getByRole('tab', { name: '登录' }).click()
  await page.getByPlaceholder('请输入用户名').fill(credentials.username)
  // SEC-FIX-2026-10-05: password 改为惰性 getter，需调用 `()`。
  // 此时才真正求值 —— 缺少环境变量时在此抛错（安全加固仍然生效），
  // 而不相关的 @smoke 用例（只 import CORS_HEADERS）不再被拖累。
  await page.getByPlaceholder('请输入密码').fill(credentials.password())
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(credentials.dashboardUrl, { timeout: 30000 })
}

export async function expectTableVisible(page: Page, index = 0) {
  await expect(page.getByRole('table').nth(index)).toBeVisible()
}

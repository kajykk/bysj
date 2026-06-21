import { expect, type Page } from '@playwright/test'

export type RoleName = 'admin' | 'counselor' | 'user'

export interface RoleFlowConfig {
  username: string
  password: string
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
    password: 'E2E@Admin123',
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
    password: 'E2E@Counselor123',
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
    username: 'user_normal',
    password: 'E2E@User123',
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

export async function loginAsRole(page: Page, role: RoleName) {
  const credentials = ROLE_FLOW_CONFIG[role]
  await page.goto('/login')
  await page.getByRole('tab', { name: '登录' }).click()
  await page.getByPlaceholder('请输入用户名').fill(credentials.username)
  await page.getByPlaceholder('请输入密码').fill(credentials.password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(credentials.dashboardUrl, { timeout: 30000 })
}

export async function expectTableVisible(page: Page, index = 0) {
  await expect(page.getByRole('table').nth(index)).toBeVisible()
}

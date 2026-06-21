import type { Page } from '@playwright/test'

type Role = 'user' | 'counselor' | 'admin'

const loginPayloads: Record<Role, { access_token: string; user: { role: Role; nickname: string; username: string } }> = {
  user: { access_token: 'user-token', user: { role: 'user', nickname: '小用户', username: 'user' } },
  counselor: { access_token: 'counselor-token', user: { role: 'counselor', nickname: '咨询师A', username: 'counselor' } },
  admin: { access_token: 'admin-token', user: { role: 'admin', nickname: '管理员', username: 'admin' } },
}

export async function mockLogin(page: Page, role: Role) {
  await page.route(/\/api\/v1\/auth\/login$/, async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: loginPayloads[role] }) })
  })
}

// Real-backend mode: keep helpers but do not mock business APIs.
export async function mockUserApi(_page: Page) {
  return undefined
}

export async function mockCounselorApi(_page: Page) {
  return undefined
}

export async function mockAdminApi(_page: Page) {
  return undefined
}

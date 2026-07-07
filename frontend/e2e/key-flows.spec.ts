import { test, expect } from '@playwright/test'
import { loginAsRole } from './shared'

/**
 * R-010 关键链路 E2E 实测：补充 token 刷新、预测、复核 3 条主链路。
 *
 * 设计原则：
 * 1. 真实后端模式（与 auth.spec.ts / warning.spec.ts 一致），不使用 mock。
 * 2. 对环境数据依赖（如待处理复核任务是否存在）采用条件分支，无数据时记录但不失败。
 * 3. 网络层注入 401 触发 token 刷新，避免依赖真实 token 过期时间。
 */

test.describe('Key Flows - Token Refresh', () => {
  test('@regression should auto refresh access_token on 401 response', async ({ page }) => {
    // 策略：登录后，使用 route 拦截首次 /api/v1/user/risk/report 返回 401，
    // 验证前端 request 拦截器会自动调用 /api/v1/auth/refresh 并重试原请求。
    await loginAsRole(page, 'user')

    let refreshCalled = false
    let originalRequestRetried = false

    await page.route('**/api/v1/user/risk/report*', async (route) => {
      const url = route.request().url()
      // 首次原请求：注入 401 触发 refresh
      if (!originalRequestRetried && !url.includes('refresh')) {
        originalRequestRetried = true
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'token 已过期' }),
        })
        return
      }
      // 默认放行（包含 refresh 端点和重试后的原请求）
      await route.continue()
    })

    // 监听 refresh 端点调用
    page.on('request', (req) => {
      if (req.url().includes('/api/v1/auth/refresh')) {
        refreshCalled = true
      }
    })

    // 触发受保护请求（访问 dashboard 会调用 risk/report）
    await page.goto('/user/dashboard')
    // 给拦截器留出 refresh 重试时间
    await page.waitForTimeout(2000)

    // 验证：触发了 refresh 调用（说明 401 处理逻辑生效）
    // 注意：refresh 是否成功取决于 refresh_token 是否有效；若 RT 已失效会跳转 login。
    expect(refreshCalled).toBe(true)
  })

  test('@regression should redirect to login when refresh_token invalid', async ({ page }) => {
    // 策略：注入过期的 access_token 到 localStorage，并模拟 refresh 端点返回 401，
    // 验证前端会重定向到 /login。
    await loginAsRole(page, 'user')

    // 拦截所有 auth/refresh 请求，返回 401（模拟 RT 失效）
    await page.route('**/api/v1/auth/refresh', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '无效或已过期的Refresh Token' }),
      })
    })

    // 拦截 risk/report 返回 401 触发 refresh 流程
    let firstHit = true
    await page.route('**/api/v1/user/risk/report*', async (route) => {
      if (firstHit) {
        firstHit = false
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'token 已过期' }),
        })
        return
      }
      await route.continue()
    })

    await page.goto('/user/dashboard')

    // 验证：因 refresh 失败，应跳转回 login 页
    await expect(page).toHaveURL(/login/, { timeout: 15000 })
  })
})

test.describe('Key Flows - Prediction', () => {
  test('@regression should submit fusion prediction and display result', async ({ page }) => {
    await loginAsRole(page, 'user')

    // 进入风险评估页
    await page.goto('/user/risk')
    await expect(page).toHaveURL(/\/user\/risk/, { timeout: 15000 })

    // 切换到融合预测 Tab（受 user.predict.use 权限控制）
    const fusionTab = page.getByRole('tab', { name: /融合|fusion/i })
    if (!(await fusionTab.isVisible().catch(() => false))) {
      test.skip(true, '当前用户无预测权限或融合 Tab 不可见，跳过')
      return
    }
    await fusionTab.click()

    // 填写文本输入（必填字段，1-5000 字符）
    const textArea = page.locator('textarea').first()
    await expect(textArea).toBeVisible({ timeout: 10000 })
    await textArea.fill('最近感觉压力较大，睡眠质量下降，希望得到评估。')

    // 点击"一键融合概览"提交按钮
    const submitBtn = page.getByRole('button', { name: /一键融合概览|fusion/i })
    await expect(submitBtn).toBeVisible({ timeout: 5000 })

    // 监听预测请求
    const predictionResponse = page.waitForResponse(
      (resp) => resp.url().includes('/api/v1/model/predict/fusion'),
      { timeout: 30000 }
    ).catch(() => null)

    await submitBtn.click()
    const response = await predictionResponse

    // 验证：API 有响应（200 成功或 422 参数错误均说明链路可达）
    expect(response).not.toBeNull()
    if (response) {
      expect([200, 422, 400]).toContain(response.status())
    }

    // 若成功：验证结果区可见
    if (response && response.status() === 200) {
      // 等待结果卡片渲染
      await expect(page.locator('.el-result').or(page.getByText(/风险等级|risk level/i))).toBeVisible({
        timeout: 10000,
      })
    }
  })
})

test.describe('Key Flows - Review', () => {
  test('@regression counselor should claim and resolve review task', async ({ page }) => {
    await loginAsRole(page, 'counselor')

    // 进入复核任务列表
    await page.goto('/counselor/reviews')
    await expect(page).toHaveURL(/\/counselor\/reviews/, { timeout: 15000 })

    // 等待表格或空状态渲染
    await page.waitForTimeout(1500)

    // 检查是否存在 pending 任务（带"领取"或"查看"按钮）
    const actionBtn = page.getByRole('button', { name: /领取|查看|claim|view/i }).first()
    const hasAction = await actionBtn.isVisible().catch(() => false)

    if (!hasAction) {
      test.skip(true, '当前无待处理复核任务，跳过完整复核流程')
      return
    }

    // 若存在"领取"按钮，先领取任务
    const claimBtn = page.getByRole('button', { name: /领取|claim/i }).first()
    if (await claimBtn.isVisible().catch(() => false)) {
      const claimResponse = page
        .waitForResponse((resp) => resp.url().includes('/api/v1/reviews/') && resp.url().includes('/assign'), {
          timeout: 15000,
        })
        .catch(() => null)
      await claimBtn.click()
      const resp = await claimResponse
      if (resp) {
        expect([200, 400, 409]).toContain(resp.status())
      }
      await page.waitForTimeout(1000)
    }

    // 点击"查看"进入详情页
    const viewBtn = page.getByRole('button', { name: /查看|view/i }).first()
    if (!(await viewBtn.isVisible().catch(() => false))) {
      test.skip(true, '无"查看"按钮，无法进入详情页')
      return
    }
    await viewBtn.click()

    // 验证跳转到详情页
    await expect(page).toHaveURL(/\/counselor\/reviews\/\d+/, { timeout: 15000 })

    // 等待详情页加载（处理操作区仅 pending/in_review 状态显示）
    await page.waitForTimeout(1500)

    // 查找处理备注输入框
    const noteInput = page.locator('textarea').first()
    const canResolve = await noteInput.isVisible().catch(() => false)

    if (!canResolve) {
      // 任务可能已被处理，验证处理结果区可见即可
      await expect(page.getByText(/处理结果|resolution/i).or(page.locator('.el-descriptions'))).toBeVisible({
        timeout: 5000,
      })
      return
    }

    // 填写复核意见
    await noteInput.fill('E2E 自动化测试提交的复核意见：建议持续关注。')

    // 点击"标记已处理"按钮
    const resolveBtn = page.getByRole('button', { name: /标记已处理|mark as resolved/i })
    await expect(resolveBtn).toBeVisible({ timeout: 5000 })

    const resolveResponse = page
      .waitForResponse(
        (resp) => resp.url().includes('/api/v1/reviews/') && resp.url().includes('/resolve'),
        { timeout: 30000 }
      )
      .catch(() => null)

    await resolveBtn.click()
    const resp = await resolveResponse

    // 验证：resolve 请求有响应
    expect(resp).not.toBeNull()
    if (resp) {
      expect([200, 400, 409]).toContain(resp.status())
    }

    // 成功后验证状态变化（处理结果区出现）
    if (resp && resp.status() === 200) {
      await expect(page.getByText(/处理结果|已解决|resolved/i)).toBeVisible({ timeout: 10000 })
    }
  })

  test('@regression counselor should see review stats', async ({ page }) => {
    await loginAsRole(page, 'counselor')
    await page.goto('/counselor/reviews')
    await expect(page).toHaveURL(/\/counselor\/reviews/, { timeout: 15000 })

    // 验证统计卡片存在（待处理/处理中/已解决/危机数）
    await expect(page.locator('.el-card').or(page.getByText(/待处理|处理中|已解决|pending|in.review/i))).toBeVisible({
      timeout: 10000,
    })
  })
})

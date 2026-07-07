// 截图脚本 - 使用项目已安装的 Playwright
import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const BASE_URL = 'http://127.0.0.1:5173';
const OUT_DIR = path.join(__dirname, '..', 'public', 'screenshots');

// 用户和咨询师 token 注入
const USER_AUTH = {
  token: 'demo-user-token-for-screenshots',
  user: {
    id: 1,
    username: 'demo_user',
    role: 'user',
    nickname: '演示用户',
  }
};

const COUNSELOR_AUTH = {
  token: 'demo-counselor-token-for-screenshots',
  user: {
    id: 2,
    username: 'demo_counselor',
    role: 'counselor',
    nickname: '演示咨询师',
  }
};

const ADMIN_AUTH = {
  token: 'demo-admin-token-for-screenshots',
  user: {
    id: 3,
    username: 'demo_admin',
    role: 'admin',
    nickname: '演示管理员',
  }
};

// 5 张核心截图配置
const SCREENSHOTS = [
  { name: '01-user-dashboard',     role: 'user',      auth: USER_AUTH,      url: '/user/dashboard',   desc: '用户仪表盘' },
  { name: '02-risk-assessment',     role: 'user',      auth: USER_AUTH,      url: '/user/risk',        desc: '多模态风险评估' },
  { name: '03-real-time-warning',   role: 'user',      auth: USER_AUTH,      url: '/user/warnings',    desc: '实时预警监控' },
  { name: '04-model-management',    role: 'admin',     auth: ADMIN_AUTH,     url: '/admin/dashboard',  desc: '模型治理中心' },
  { name: '05-report-center',       role: 'user',      auth: USER_AUTH,      url: '/user/assessments', desc: '报告中心' },
];

async function ensureDir(p) {
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
}

async function setAuth(context, auth) {
  // 在 context 级别注入：每次导航前自动执行
  await context.addInitScript((auth) => {
    try {
      // ISS-008: token 存 sessionStorage
      window.sessionStorage.setItem('token', auth.token);
      // user 存 localStorage
      window.localStorage.setItem('user', JSON.stringify(auth.user));
    } catch (e) {
      console.error('Failed to set auth', e);
    }
  }, auth);
}

async function takeScreenshot(browser, shot) {
  console.log(`\n📸 ${shot.name}: ${shot.desc} (${shot.url})`);

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2, // retina 高清
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  });

  // 注入 token（在 context 级别，每次页面加载前都执行）
  await setAuth(context, shot.auth);

  const page = await context.newPage();

  // 拦截后端 API 请求，统统返回 mock 数据（避免 500 错误）
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    // 根据路径返回合理的 mock 数据
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockResponse(url, method)),
    });
  });

  // 先访问 / 触发 SPA 加载（让 init script 注入 sessionStorage）
  console.log(`   Step 1: Visit / to inject auth...`);
  try {
    await page.goto(`${BASE_URL}/`, {
      waitUntil: 'load',
      timeout: 15000,
    });
  } catch (e) {
    console.log(`   ⚠️  Initial navigation warning: ${e.message}`);
  }

  // 等待 auth 注入生效 & 首次渲染
  await page.waitForTimeout(1500);

  // 验证 auth 已注入
  const hasAuth = await page.evaluate(() => {
    return {
      token: !!window.sessionStorage.getItem('token'),
      user: !!window.localStorage.getItem('user')
    };
  });
  console.log(`   Auth state:`, hasAuth);

  // 现在导航到目标页面，使用 load 事件等待完整加载
  console.log(`   Step 2: Navigate to ${shot.url}...`);
  try {
    await page.goto(`${BASE_URL}${shot.url}`, {
      waitUntil: 'load',
      timeout: 30000,
    });
  } catch (e) {
    console.log(`   ⚠️  Navigation warning: ${e.message}`);
  }

  // 等待 .layout-root 元素出现（页面已挂载）
  console.log(`   Step 3: Wait for layout to render...`);
  try {
    await page.waitForSelector('.layout-root, .el-empty, .el-skeleton', {
      timeout: 15000,
    });
  } catch (e) {
    console.log(`   ⚠️  Layout selector not found, continuing anyway: ${e.message}`);
  }

  // 再等待内容稳定
  await page.waitForTimeout(3000);

  // 强制关闭任何 v-loading 全屏遮罩
  await page.evaluate(() => {
    try {
      document.querySelectorAll('.el-loading-mask, .el-overlay').forEach(el => {
        el.remove();
      });
      document.querySelectorAll('.el-loading-spinner, [v-loading]').forEach(el => {
        const mask = el.closest('.el-loading-mask');
        if (mask) mask.remove();
      });
      document.querySelectorAll('.el-loading-parent--relative').forEach(el => {
        el.classList.remove('el-loading-parent--relative');
        el.classList.remove('el-loading-parent--hidden');
      });
    } catch (e) {
      console.error('Failed to clear loading', e);
    }
  });

  await page.waitForTimeout(1000);

  // 调试：打印当前页面状态
  const pageInfo = await page.evaluate(() => {
    return {
      url: window.location.href,
      title: document.title,
      bodyText: document.body.innerText.substring(0, 200),
      bodyHtml: document.body.innerHTML.length,
      hasLayout: !!document.querySelector('.layout-root'),
      hasMain: !!document.querySelector('.layout-main'),
      hasLoading: !!document.querySelector('.el-loading-mask'),
      elLoadingParent: document.querySelectorAll('.el-loading-parent--relative').length
    };
  });
  console.log(`   Page info:`, pageInfo);

  // 截图
  const outPath = path.join(OUT_DIR, `${shot.name}.png`);
  await page.screenshot({ path: outPath, fullPage: false });
  console.log(`   ✅ Saved: ${outPath}`);

  await context.close();
}

function mockResponse(url, method) {
  // 简单的 mock 响应，避免前端因缺数据崩溃
  if (url.includes('/auth/me') || url.includes('/auth/profile')) {
    return {
      id: 1,
      username: 'demo_user',
      role: 'user',
      nickname: '演示用户',
    };
  }
  if (url.includes('/warnings')) {
    return {
      items: Array.from({ length: 8 }, (_, i) => ({
        id: i + 1,
        title: `预警 #${i + 1}`,
        content: '检测到近期情绪波动，请关注',
        risk_level: (i % 3) + 1,
        is_read: i > 2,
        status: ['pending', 'handled', 'ignored'][i % 3],
        created_at: new Date(Date.now() - i * 86400000).toISOString(),
        handled_at: i > 2 ? new Date(Date.now() - i * 86400000 + 3600000).toISOString() : null,
      })),
      total: 8,
      page: 1,
      page_size: 10,
    };
  }
  if (url.includes('/assessments')) {
    return {
      items: Array.from({ length: 5 }, (_, i) => ({
        id: i + 1,
        risk_score: 0.3 + i * 0.15,
        risk_level: ['low', 'medium', 'high'][i % 3],
        created_at: new Date(Date.now() - i * 7 * 86400000).toISOString(),
        summary: '综合评估结果',
      })),
      total: 5,
      page: 1,
      page_size: 10,
    };
  }
  if (url.includes('/risk')) {
    return {
      risk_score: 0.45,
      risk_level: 'medium',
      modalities: { structured: 0.4, text: 0.5, physio: 0.3 },
      recommendations: ['建议每周复评', '关注睡眠质量', '保持运动习惯'],
    };
  }
  // 通用空响应
  return { items: [], total: 0, page: 1, page_size: 10 };
}

async function main() {
  await ensureDir(OUT_DIR);

  console.log(`📁 Output directory: ${OUT_DIR}`);
  console.log(`🌐 Base URL: ${BASE_URL}`);

  const browser = await chromium.launch({
    headless: true,
    channel: 'msedge',  // 使用系统已安装的 Edge
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });

  try {
    for (const shot of SCREENSHOTS) {
      await takeScreenshot(browser, shot);
    }
    console.log(`\n🎉 全部完成！共 ${SCREENSHOTS.length} 张截图已保存到 ${OUT_DIR}`);
  } catch (err) {
    console.error('❌ Error:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();

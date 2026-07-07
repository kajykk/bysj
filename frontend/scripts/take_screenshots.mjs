// 截图脚本 - 真实后端登录 + 真实数据（无 mock）
import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const BASE_URL = 'http://127.0.0.1:5173';
const API_BASE = 'http://127.0.0.1:8000';
const OUT_DIR = path.join(__dirname, '..', 'public', 'screenshots');

// 真实账号（来自 backend/.env E2E 密码 + seed 数据）
const USER_CREDENTIALS = { username: 'user_moderate', password: 'E2E@User123' };
const ADMIN_CREDENTIALS = { username: 'admin', password: 'E2E@Admin123' };

// 5 张核心截图配置
const SCREENSHOTS = [
  { name: '01-user-dashboard',     url: '/user/dashboard',      desc: '用户仪表盘',         creds: USER_CREDENTIALS },
  { name: '02-risk-assessment',     url: '/user/risk',           desc: '多模态风险评估',     creds: USER_CREDENTIALS },
  { name: '03-real-time-warning',   url: '/user/warnings',       desc: '实时预警监控',       creds: USER_CREDENTIALS },
  { name: '04-model-training',      url: '/user/model-training', desc: 'ML 训练与实验中心',  creds: USER_CREDENTIALS },
  { name: '05-report-center',       url: '/user/assessments',    desc: '评估报告中心',       creds: USER_CREDENTIALS },
];

async function ensureDir(p) {
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
}

// 通过真实 API 登录，获取 JWT token 和 user 信息
async function login(creds) {
  const resp = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(creds),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Login failed for ${creds.username}: ${resp.status} ${text}`);
  }
  const json = await resp.json();
  return {
    token: json.data.access_token,
    user: json.data.user,
  };
}

async function takeScreenshot(browser, shot) {
  console.log(`\n📸 ${shot.name}: ${shot.desc} (${shot.url})`);

  // 1. 真实登录
  console.log(`   Logging in as ${shot.creds.username}...`);
  const auth = await login(shot.creds);
  console.log(`   ✅ Token obtained (user: ${auth.user.username}, role: ${auth.user.role})`);

  // 2. 创建浏览器上下文
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  });

  // 3. 注入真实 token（每次导航前自动执行）
  await context.addInitScript((auth) => {
    try {
      window.sessionStorage.setItem('token', auth.token);
      window.localStorage.setItem('user', JSON.stringify(auth.user));
    } catch (e) {
      console.error('Failed to set auth', e);
    }
  }, auth);

  const page = await context.newPage();

  // 4. 先访问 / 让 SPA 加载 + auth 注入
  console.log(`   Step 1: Visit / to bootstrap SPA + inject auth...`);
  try {
    await page.goto(`${BASE_URL}/`, {
      waitUntil: 'load',
      timeout: 15000,
    });
  } catch (e) {
    console.log(`   ⚠️  Initial navigation warning: ${e.message}`);
  }

  await page.waitForTimeout(1500);

  // 5. 导航到目标页面
  console.log(`   Step 2: Navigate to ${shot.url}...`);
  try {
    await page.goto(`${BASE_URL}${shot.url}`, {
      waitUntil: 'load',
      timeout: 30000,
    });
  } catch (e) {
    console.log(`   ⚠️  Navigation warning: ${e.message}`);
  }

  // 6. 等待页面内容渲染
  console.log(`   Step 3: Wait for content to render...`);
  try {
    await page.waitForSelector('.layout-root', { timeout: 15000 });
    console.log(`   ✅ Layout found`);
  } catch (e) {
    console.log(`   ⚠️  Layout not found, continuing...`);
  }

  // 等待数据加载完成（skeleton 消失或内容出现）
  await page.waitForTimeout(5000);

  // 7. 清除可能残留的 loading 遮罩
  await page.evaluate(() => {
    document.querySelectorAll('.el-loading-mask, .el-overlay').forEach(el => el.remove());
  });

  await page.waitForTimeout(500);

  // 8. 调试日志
  const pageInfo = await page.evaluate(() => ({
    url: window.location.href,
    bodyTextLen: document.body.innerText.length,
    hasLayout: !!document.querySelector('.layout-root'),
    hasMain: !!document.querySelector('.layout-main'),
  }));
  console.log(`   Page info:`, pageInfo);

  // 9. 截图
  const outPath = path.join(OUT_DIR, `${shot.name}.png`);
  await page.screenshot({ path: outPath, fullPage: false });
  console.log(`   ✅ Saved: ${outPath}`);

  await context.close();
}

async function main() {
  await ensureDir(OUT_DIR);

  console.log(`📁 Output directory: ${OUT_DIR}`);
  console.log(`🌐 Frontend: ${BASE_URL}`);
  console.log(`🔌 Backend:  ${API_BASE}`);

  const browser = await chromium.launch({
    headless: true,
    channel: 'msedge',
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

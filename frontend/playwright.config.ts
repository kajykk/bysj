import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, devices } from '@playwright/test'

const frontendUrl = 'http://localhost:5173'
const backendUrl = 'http://127.0.0.1:8000'
const currentDir = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = currentDir
const rootDir = path.resolve(currentDir, '..')
const backendDir = path.join(rootDir, 'backend')

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['html', { outputFolder: 'playwright-report' }]],
  use: {
    baseURL: frontendUrl,
    trace: 'on-first-retry',
    headless: true,
    launchOptions: {
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    },
  },
  grep: process.env.E2E_TAG ? new RegExp(process.env.E2E_TAG) : undefined,
  projects: [
    {
      name: 'chromium',
      testMatch: /.*\.spec\.ts$/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'chromium-smoke',
      testMatch: /.*\.spec\.ts$/,
      grep: /@smoke/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'chromium-regression',
      testMatch: /.*\.spec\.ts$/,
      grep: /@regression/,
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: process.platform === 'win32' ? 'npm.cmd run dev' : 'npm run dev',
    url: frontendUrl,
    reuseExistingServer: true,
    timeout: 600000,
    cwd: frontendDir,
    env: {
      VITE_API_BASE_URL: `${backendUrl}/api/v1`,
    },
  },
})

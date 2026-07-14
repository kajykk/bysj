import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [
    vue(),
    // 与 vite.config.ts 保持一致，使 Element Plus 组件在测试环境中可被自动解析
    // importStyle: false 避免在 jsdom 中加载 CSS 文件导致 "Unknown file extension .css" 错误
    Components({
      resolvers: [ElementPlusResolver({ importStyle: false })],
      dts: false,
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@common': fileURLToPath(new URL('../common', import.meta.url))
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.ts', 'src/**/*.test.js'],
    testTimeout: 30000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      reportsDirectory: 'coverage',
      // MAINT-P3-001: 覆盖率门禁 (渐进式提升路线图: 50% → 60% → 70% → 85%)
      // 当前基线未知, 先设 50% 保守起点, 与 backend --cov-fail-under=50 一致
      thresholds: {
        lines: 50,
        functions: 50,
        branches: 40,
        statements: 50
      }
    }
  }
})

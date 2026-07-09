import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ command }) => ({
  // M-FE-22 修复：esbuild 顶层配置，仅 build 时 drop console/debugger，避免影响 dev 调试
  esbuild: {
    drop: command === 'build' ? ['console', 'debugger'] : undefined,
  },
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      manifest: {
        name: '抑郁症动态预警与干预系统',
        short_name: '抑郁预警系统',
        description: '基于多模态数据的智能风险评估平台',
        theme_color: '#2e6fa8',
        background_color: '#ffffff',
        display: 'standalone',
        scope: '/',
        start_url: '/',
        icons: [
          {
            src: '/icon-192x192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: '/icon-512x512.png',
            sizes: '512x512',
            type: 'image/png',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        globDirectory: 'dist',
        runtimeCaching: [
          {
            // P1-P5 修复：原 urlPattern 仅匹配 localhost，生产环境 API 请求不会被缓存。
            // 改为匹配任意 origin 下的 /api/ 路径，兼容本地开发、局域网和生产部署。
            urlPattern: /^https?:\/\/[^/]+\/api\/.*$/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 60 * 60 * 24,
              },
              networkTimeoutSeconds: 3,
            },
          },
          {
            urlPattern: /\.(?:png|jpg|jpeg|svg|gif)$/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'image-cache',
              expiration: {
                maxEntries: 50,
                maxAgeSeconds: 60 * 60 * 24 * 7,
              },
            },
          },
          {
            urlPattern: /\.(?:woff2|woff|ttf)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'font-cache',
              expiration: {
                maxEntries: 20,
                maxAgeSeconds: 60 * 60 * 24 * 365,
              },
            },
          },
        ],
        navigateFallback: '/offline.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/ws\//],
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
      },
      devOptions: {
        enabled: false,
      },
    }),
    AutoImport({
      imports: ['vue', 'vue-router', 'pinia'],
      resolvers: [ElementPlusResolver()],
      dts: 'src/auto-imports.d.ts',
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      dts: 'src/components.d.ts',
    }),
  ],
  define: {
    __CSP_NONCE__: JSON.stringify(process.env.VITE_CSP_NONCE || ''),
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // L-FE-1 修复：为跨项目共享的 common 目录提供别名，替代脆弱的 ../../../ 相对路径
      '@common': fileURLToPath(new URL('../common', import.meta.url))
    }
  },
  build: {
    // 性能优化：Brotli 预压缩可在生产环境进一步降低传输体积（比 gzip 小 15-25%）
    // 启用方式：安装 vite-plugin-compression2 后在 plugins 中添加 brotli({ deleteOriginalAssets: false })
    // 当前由 nginx 负责 gzip 压缩；若 nginx 已启用 ngx_brotli 模块，可在此预生成 .br 文件以省去运行时压缩开销
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          // H-20 修复：调整匹配顺序，把更具体的匹配放在前面，避免被宽泛匹配误捕获
          // 使用路径分隔符匹配，避免 'vue' 误匹配 'vue-i18n'、'vue-router' 等

          // Icons (必须先于 element-plus 匹配，因为 @element-plus/icons-vue 包含 element-plus)
          if (id.includes('@element-plus/icons-vue')) return 'icons'
          // Router & state management (必须先于 vue 匹配，因为 vue-router 包含 vue)
          if (id.includes('vue-router')) return 'router'
          if (id.includes('vue-i18n')) return 'i18n'
          if (id.includes('pinia')) return 'state'
          // Core vue framework (精确匹配，避免匹配 vue-router/vue-i18n)
          // 包含 @vue/* 运行时包 (runtime-dom/reactivity/shared 等)
          if (/[\\/]node_modules[\\/](@vue|vue)[\\/]/.test(id)) return 'vue-core'
          // element-plus 分组拆分，减少主 chunk 体积（R-008 修复）
          // 原方案：所有 element-plus 组件打包到单一 chunk（738 KB）
          // 新方案：按组件类型拆分为子 chunk，首屏仅需加载核心组件
          // 注意：ep-form 已合并回 element-plus 主 chunk，因 form 组件与 core 存在循环依赖
          if (id.includes('element-plus')) {
            // 表格类重组件（Table/TableColumn/Pagination），仅列表页需要
            if (/[\\/]components[\\/](table|pagination)[\\/]/.test(id)) return 'ep-table'
            // 弹层类重组件（Dialog/Drawer），仅交互时需要
            if (/[\\/]components[\\/](dialog|drawer)[\\/]/.test(id)) return 'ep-overlay'
            // 展示类重组件（Descriptions/Steps/Timeline/Tabs），仅详情页需要
            if (/[\\/]components[\\/](descriptions|steps|timeline|tabs)[\\/]/.test(id)) return 'ep-display'
            // 核心组件 + 表单类组件保留在主 element-plus chunk
            // 表单类组件 (Select/DatePicker/Cascader 等) 与 core 存在双向引用，拆分会导致循环 chunk
            return 'element-plus'
          }
          // Charts - R-007 优化：移除未使用的 RadarChart/RadarComponent 后体积降至 462.80 KB
          // 仅匹配 echarts 路径，zrender 作为 echarts 依赖会被自动捕获进同一 chunk。
          // 注意：若显式匹配 zrender 会将原本在 vendor chunk 中的 zrender 代码拉入，
          // 导致 charts chunk 从 462.80 KB 上涨到 631.40 KB。
          // 通过路由懒加载确保仅图表页面加载此 chunk。
          if (id.includes('echarts')) return 'charts'
          // Utilities
          if (id.includes('dompurify')) return 'security'
          if (id.includes('axios')) return 'http'
          // Default vendor chunk
          return 'vendor'
        },
        // Optimize chunk loading
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: (assetInfo) => {
          const info = assetInfo.name || ''
          if (info.endsWith('.css')) return 'assets/[name]-[hash][extname]'
          if (info.endsWith('.png') || info.endsWith('.jpg') || info.endsWith('.jpeg') || info.endsWith('.gif') || info.endsWith('.svg')) {
            return 'assets/images/[name]-[hash][extname]'
          }
          return 'assets/[name]-[hash][extname]'
        },
      }
    },
    chunkSizeWarningLimit: 1000,
    sourcemap: false,
    // M-FE-22 修复：改用 esbuild 压缩（比 terser 快 20-40 倍），
    // drop console/debugger 配置已移至顶层 esbuild 选项（仅 build 时生效）
    minify: 'esbuild',
    // 性能优化：CSS 代码分割
    cssCodeSplit: true,
    // 性能优化：预加载关键资源
    reportCompressedSize: false,
    // 性能优化：预渲染关键路由
    dynamicImportVarsOptions: {
      warnOnError: true,
      exclude: [/node_modules/],
    },
  },
  // 性能优化：模块预加载
  optimizeDeps: {
    include: [
      'vue',
      'vue-router',
      'pinia',
      '@element-plus/icons-vue',
      'axios',
      'echarts/core',
      'echarts/charts',
      'echarts/components',
      'echarts/renderers',
    ],
    exclude: [],
  },
  test: {
    environment: 'jsdom',
    deps: {
      optimizer: {
        web: {
          include: ['vue', 'vue-router', 'pinia', 'element-plus', '@element-plus/icons-vue'],
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        // L-修复：后端实际监听 8000 端口（见 Dockerfile/CI 脚本），修正代理目标端口
        target: process.env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true
      },
      '/ws': {
        target: process.env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8000',
        ws: true
      }
    }
  }
}))

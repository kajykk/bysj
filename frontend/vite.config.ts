import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      manifest: {
        name: '抑郁症动态预警与干预系统',
        short_name: '抑郁预警系统',
        description: '基于多模态数据的智能风险评估平台',
        theme_color: '#409eff',
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
            urlPattern: /^https:\/\/localhost:\d+\/api\/.*$/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 60 * 60 * 24,
              },
              networkTimeoutSeconds: 10,
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
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          // Core framework + UI library (merged to prevent circular: ui ↔ vue-core)
          if (id.includes('vue') && !id.includes('vue-router')) return 'vue-core'
          if (id.includes('element-plus')) return 'vue-core'
          // Router & state management
          if (id.includes('vue-router')) return 'router'
          if (id.includes('pinia')) return 'state'
          // Icons
          if (id.includes('@element-plus/icons-vue')) return 'icons'
          // Charts
          if (id.includes('echarts')) return 'charts'
          // Export / file processing libraries
          if (id.includes('xlsx') || id.includes('sheetjs')) return 'export-excel'
          if (id.includes('jspdf') || id.includes('html2canvas') || id.includes('html2pdf')) return 'export-pdf'
          // Utilities
          if (id.includes('dayjs')) return 'datetime'
          if (id.includes('dompurify')) return 'security'
          if (id.includes('axios')) return 'http'
          if (id.includes('vue-i18n')) return 'i18n'
          if (id.includes('lodash') || id.includes('underscore')) return 'utils'
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
    chunkSizeWarningLimit: 500,
    sourcemap: true,
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
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
      'element-plus',
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
        target: process.env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8001',
        changeOrigin: true
      },
      '/ws': {
        target: process.env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8001',
        ws: true
      }
    }
  }
})

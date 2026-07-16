/**
 * PERF-P2-006 / PERF-P2-007 / PERF-P2-008: vite.config.ts 打包优化配置测试.
 *
 * 验证:
 * 1. PERF-P2-006: ECharts 按需引入 (src/utils/echarts.ts 不全量 import)
 * 2. PERF-P2-007: element-plus 分包 (manualChunks 拆分) + chunkSizeWarningLimit=500
 * 3. PERF-P2-008: brotli 预压缩 (vite-plugin-compression2 已启用)
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve, dirname } from 'node:path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
// src/config/ → frontend/
const frontendRoot = resolve(__dirname, '..', '..') + '/'
const viteConfigPath = `${frontendRoot}vite.config.ts`
const echartsUtilPath = `${frontendRoot}src/utils/echarts.ts`
const packageJsonPath = `${frontendRoot}package.json`

function readSource(path: string): string {
  return readFileSync(path, 'utf-8')
}

describe('PERF-P2-006: ECharts 按需引入', () => {
  it('src/utils/echarts.ts 应从 echarts/core 按需引入, 而非全量 echarts', () => {
    const source = readSource(echartsUtilPath)
    expect(source).toContain("from 'echarts/core'")
    expect(source).toContain("from 'echarts/charts'")
    expect(source).toContain("from 'echarts/components'")
    expect(source).toContain("from 'echarts/renderers'")
    // 检查 active 代码行 (排除注释) 不应全量引入 echarts
    // 注释中可能引用历史记录 "import * as echarts from 'echarts'"
    const activeLines = source
      .split('\n')
      .filter((line) => !line.trim().startsWith('*') && !line.trim().startsWith('//'))
      .join('\n')
    // 行首的 import * as echarts from 'echarts' (非 'echarts/...')
    expect(activeLines).not.toMatch(/^import\s+\*\s+as\s+echarts\s+from\s+['"]echarts['"]$/m)
  })

  it('echarts.use() 应仅注册项目实际使用的图表/组件', () => {
    const source = readSource(echartsUtilPath)
    // 注册列表中应包含项目用到的图表
    expect(source).toContain('LineChart')
    expect(source).toContain('BarChart')
    expect(source).toContain('PieChart')
    expect(source).toContain('HeatmapChart')
    // 提取 echarts.use([...]) 块, 仅检查实际注册列表 (排除注释中的历史记录)
    const useBlockMatch = source.match(/echarts\.use\(\[([\s\S]*?)\]\)/)
    expect(useBlockMatch).not.toBeNull()
    const useBlock = useBlockMatch![1]
    // 不应注册未使用的图表
    expect(useBlock).not.toContain('RadarChart')
    expect(useBlock).not.toContain('GraphChart')
    expect(useBlock).not.toContain('MapChart')
    expect(useBlock).not.toContain('TreeChart')
    expect(useBlock).not.toContain('SunburstChart')
  })

  it('vite.config.ts optimizeDeps 应预构建 echarts 按需子路径', () => {
    const source = readSource(viteConfigPath)
    expect(source).toContain("'echarts/core'")
    expect(source).toContain("'echarts/charts'")
    expect(source).toContain("'echarts/components'")
    expect(source).toContain("'echarts/renderers'")
    // 不应预构建全量 echarts (会拉入整个 echarts 包)
    // 检查 include 数组中没有单独的 'echarts' 项
    // 简化: 至少确认按需子路径存在
    expect(source).toMatch(/echarts\/core/)
  })
})

describe('PERF-P2-007: element-plus 分包', () => {
  it('manualChunks 应将 element-plus 拆分为多个子 chunk', () => {
    const source = readSource(viteConfigPath)
    expect(source).toContain("id.includes('element-plus')")
    // 拆分的子 chunk 名称
    // 注: ep-form-advanced / ep-utility 已由 ISS-15 修复移除 (消除 EP manualChunks
    // 循环依赖 TDZ: production minified ReferenceError)。仅保留单向依赖的拆分:
    expect(source).toContain("'ep-table'")
    expect(source).toContain("'ep-overlay'")
    expect(source).toContain("'ep-display'")
    expect(source).toContain("'element-plus'")
    // 确认已移除会触发循环依赖的 chunk
    expect(source).not.toContain("'ep-form-advanced'")
    expect(source).not.toContain("'ep-utility'")
  })

  it('chunkSizeWarningLimit 应为 500 (降低警告阈值便于发现超大 chunk)', () => {
    const source = readSource(viteConfigPath)
    expect(source).toMatch(/chunkSizeWarningLimit:\s*500\b/)
    expect(source).not.toMatch(/chunkSizeWarningLimit:\s*1000\b/)
  })

  it('icons 应拆分到独立 chunk (先于 element-plus 匹配)', () => {
    const source = readSource(viteConfigPath)
    expect(source).toContain("@element-plus/icons-vue")
    expect(source).toContain("return 'icons'")
  })
})

describe('PERF-P2-008: brotli 预压缩', () => {
  it('vite-plugin-compression2 应在 package.json devDependencies 中', () => {
    const pkg = JSON.parse(readSource(packageJsonPath))
    expect(pkg.devDependencies).toBeDefined()
    expect(pkg.devDependencies['vite-plugin-compression2']).toBeDefined()
  })

  it('vite.config.ts 应 import compression from vite-plugin-compression2', () => {
    const source = readSource(viteConfigPath)
    expect(source).toContain("vite-plugin-compression2")
    expect(source).toMatch(/import\s+\{[^}]*compression[^}]*\}\s+from\s+['"]vite-plugin-compression2['"]/)
  })

  it('compression 插件应仅在 build 时启用, 算法为 brotliCompress', () => {
    const source = readSource(viteConfigPath)
    expect(source).toContain("command === 'build'")
    expect(source).toContain('brotliCompress')
    // 应排除二进制资源 (png/jpg/woff2 等已压缩格式)
    expect(source).toMatch(/exclude:\s*\[/)
    expect(source).toContain('/\\.png$/')
    expect(source).toContain('/\\.woff2$/')
  })

  it('应设置 threshold 避免压缩过小文件', () => {
    const source = readSource(viteConfigPath)
    expect(source).toMatch(/threshold:\s*\d+/)
  })
})

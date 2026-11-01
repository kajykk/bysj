import fs from 'node:fs'
import path from 'node:path'
import './styles/variables.scss'

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
})

Object.defineProperty(navigator, 'sendBeacon', {
  writable: true,
  value: () => true,
})

// jsdom 不会计算样式表里的 CSS 自定义属性（getComputedStyle 拿不到 :root 的 --x）。
// 从真实的 variables.scss 解析后注入，替代原先手写的 5 个变量副本 ——
// 否则 token 改了测试仍然绿，样式门禁是假的。
// 注意: 不能用 `?raw` 导入 —— Vitest 默认 css:false 会把 scss 导入解析为空串。
const variablesScss = fs.readFileSync(
  path.resolve(process.cwd(), 'src/styles/variables.scss'),
  'utf8',
)

for (const match of variablesScss.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) {
  document.documentElement.style.setProperty(`--${match[1]}`, match[2].trim())
}

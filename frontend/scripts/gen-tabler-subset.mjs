import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// 只打入实际用到的图标：完整 Tabler 集合 gzip 约 350KB，超出 UI-B3 的 80KB 预算。
const ICON_NAMES = [
  'alert-triangle',
  'arrow-down',
  'arrow-up',
  'bell',
  'book',
  'calendar',
  'chart-line',
  'chevron-down',
  'circle-half-2',
  'clock',
  'copy',
  'device-desktop',
  'file-text',
  'help-circle',
  'home',
  'layout-sidebar-left-collapse',
  'layout-sidebar-left-expand',
  'link',
  'logout',
  'menu-2',
  'message-circle',
  'moon',
  'palette',
  'pencil',
  'phone',
  'rocket',
  'settings',
  'sun',
  'user',
  'users',
]

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const source = JSON.parse(
  fs.readFileSync(path.join(root, 'node_modules/@iconify-json/tabler/icons.json'), 'utf8'),
)

const icons = {}
for (const name of ICON_NAMES) {
  if (!source.icons[name]) throw new Error(`Tabler 图标不存在: ${name}`)
  icons[name] = source.icons[name]
}

const subset = {
  prefix: 'tabler',
  width: source.width,
  height: source.height,
  icons,
}

const header = `// 由 frontend/scripts/gen-tabler-subset.mjs 生成，请勿手改。
// 新增图标：编辑脚本里的 ICON_NAMES 后运行 node scripts/gen-tabler-subset.mjs
import type { IconifyJSON } from '@iconify/vue'

const tablerSubset = `

const output = `${header}${JSON.stringify(subset, null, 2)} satisfies IconifyJSON

export default tablerSubset
`

fs.mkdirSync(path.join(root, 'src/icons'), { recursive: true })
fs.writeFileSync(path.join(root, 'src/icons/tabler-subset.ts'), output)
console.log(`tabler-subset.ts: ${ICON_NAMES.length} icons`)

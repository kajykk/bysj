import { createI18n } from 'vue-i18n'
// M-28 修复：同步导入默认语言包（zh-CN），确保首屏渲染时已有翻译消息
// 避免异步加载导致首屏显示翻译 key
import zhCNMessages from './locales/zh-CN'

const isDev = import.meta.env.DEV

const ALLOWED_LOCALES = ['zh-CN', 'en-US'] as const
type AppLocale = (typeof ALLOWED_LOCALES)[number]

const isAllowedLocale = (value: string | null): value is AppLocale =>
  !!value && (ALLOWED_LOCALES as readonly string[]).includes(value)

const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  messageCompiler: isDev ? undefined : false,
  locale: (() => {
    const stored = localStorage.getItem('locale')
    return isAllowedLocale(stored) ? stored : 'zh-CN'
  })(),
  fallbackLocale: 'zh-CN',
  // M-28 修复：默认语言包同步加载，确保首屏不显示翻译 key
  // zh-CN.ts 使用 `export default {...}`，import default 直接得到对象本身，无需 .default 访问
  messages: {
    'zh-CN': zhCNMessages,
  },
})

// FC-02 修复：i18n.global 在 composition 模式下的 locale.value 类型被推断为 "zh-CN" 字面量，
// 此处通过类型断言放宽为 AppLocale，以支持运行时切换到 en-US 等其他语言。
const i18nGlobal = i18n.global as unknown as {
  availableLocales: string[]
  setLocaleMessage(locale: AppLocale, messages: Record<string, unknown>): void
  locale: { value: AppLocale }
}

// 按需加载语言包
// M-FE-8 修复：使用显式映射对象替代动态 import 模板字符串，便于静态分析和打包分析
// zh-CN 已在顶部静态导入，此处仅包含需要异步加载的语言包
const localeLoaders: Partial<Record<AppLocale, () => Promise<{ default: Record<string, unknown> }>>> = {
  'en-US': () => import('./locales/en-US'),
}

export async function loadLocaleMessages(locale: AppLocale | string) {
  const target: AppLocale = isAllowedLocale(locale) ? locale : 'zh-CN'
  // 避免重复加载
  if (i18nGlobal.availableLocales.includes(target)) return

  const loader = localeLoaders[target]
  if (!loader) return  // zh-CN 已静态加载，无需异步导入

  try {
    const messages = await loader()
    i18nGlobal.setLocaleMessage(target, messages.default)
    i18nGlobal.locale.value = target
    localStorage.setItem('locale', target)
  } catch (error) {
    // L-FE-4 修复：语言包加载失败为非致命错误，降级为 console.warn 避免被误判为严重故障
    console.warn(`Failed to load locale ${target}:`, error)
  }
}

// 初始化加载当前语言（zh-CN 已同步加载，其他语言异步加载）
const defaultLocale = String(i18nGlobal.locale.value || 'zh-CN')
if (defaultLocale !== 'zh-CN') {
  loadLocaleMessages(defaultLocale)
}

export function translate(key: string, named?: Record<string, unknown>): string {
  const t = i18n.global.t as unknown as (key: string, named?: Record<string, unknown>) => string
  return named ? t(key, named) : t(key)
}

export default i18n

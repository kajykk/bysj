import { createI18n } from 'vue-i18n'

const ALLOWED_LOCALES = ['zh-CN', 'en-US']

const i18n = createI18n({
  legacy: false,
  locale: (() => {
    const stored = localStorage.getItem('locale')
    return stored && ALLOWED_LOCALES.includes(stored) ? stored : 'zh-CN'
  })(),
  fallbackLocale: 'zh-CN',
  messages: {}
})

// 按需加载语言包
export async function loadLocaleMessages(locale: string) {
  if (!locale || !ALLOWED_LOCALES.includes(locale)) {
    locale = 'zh-CN'
  }
  // 避免重复加载
  if (i18n.global.availableLocales.includes(locale)) return

  try {
    const messages = await import(`./locales/${locale}.ts`)
    i18n.global.setLocaleMessage(locale, messages.default)
    i18n.global.locale.value = locale
    localStorage.setItem('locale', locale)
  } catch (error) {
    console.error(`Failed to load locale ${locale}:`, error)
  }
}

// 初始化加载默认语言
const defaultLocale = String(i18n.global.locale.value || 'zh-CN')
loadLocaleMessages(defaultLocale)

export default i18n

import type { ConfigItem } from '@/api/adminApi'

/**
 * AdminSettings 共享工具函数。
 * 从原 AdminSettingsPage.vue 提取，供 SecurityTab/NotificationTab 共享使用。
 */
export const getConfigValue = <T,>(configs: ConfigItem[], key: string, fallback: T): T => {
  const item = configs.find((c) => c.config_key === key)
  if (!item) return fallback
  const val = (item.config_value as Record<string, unknown>)?.value
  return (val as T) ?? fallback
}

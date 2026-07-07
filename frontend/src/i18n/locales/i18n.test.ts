import { describe, it, expect } from 'vitest'
import zhCN from './zh-CN'
import enUS from './en-US'

/**
 * i18n 语言包键值完整性测试（T-306: 文档国际化补全 en-US 100%）
 *
 * 与原 mock 测试不同，本测试直接导入真实的 zh-CN.ts 与 en-US.ts，
 * 通过递归比较确保两个语言包的键路径集合完全一致，避免出现 en-US 缺失翻译键的情况。
 *
 * 覆盖：
 * 1. 真实 locale 文件键结构一致性（递归比对）
 * 2. 所有键值非空（避免空字符串/未翻译占位）
 * 3. 中英文内容确实不同（防止复制粘贴未翻译）
 * 4. 命名规范（camelCase，顶级命名空间合法）
 * 5. 命名空间覆盖性检查（common/nav/layout/role/user/theme/language/monitoring/report/error）
 */

type StringDict = Record<string, unknown>

/**
 * 递归获取对象的所有键路径（叶子节点）
 * 例如 { a: { b: 1 } } => ['a.b']
 */
const getKeyPaths = (obj: StringDict, prefix = ''): string[] => {
  const paths: string[] = []
  for (const key of Object.keys(obj)) {
    const path = prefix ? `${prefix}.${key}` : key
    const value = obj[key]
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      paths.push(...getKeyPaths(value as StringDict, path))
    } else {
      paths.push(path)
    }
  }
  return paths
}

/**
 * 按键路径获取嵌套对象中的值
 */
const getValueByPath = (obj: StringDict, path: string): unknown => {
  return path.split('.').reduce<unknown>((acc, k) => {
    if (acc !== null && typeof acc === 'object') {
      return (acc as StringDict)[k]
    }
    return undefined
  }, obj)
}

/**
 * 递归获取所有叶子节点的 [path, value] 对
 */
const getEntries = (obj: StringDict, prefix = ''): Array<[string, unknown]> => {
  const entries: Array<[string, unknown]> = []
  for (const key of Object.keys(obj)) {
    const path = prefix ? `${prefix}.${key}` : key
    const value = obj[key]
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      entries.push(...getEntries(value as StringDict, path))
    } else {
      entries.push([path, value])
    }
  }
  return entries
}

const zhCNObj = zhCN as unknown as StringDict
const enUSObj = enUS as unknown as StringDict

const zhKeyPaths = getKeyPaths(zhCNObj).sort()
const enKeyPaths = getKeyPaths(enUSObj).sort()

describe('i18n 语言包完整性测试（T-306）', () => {
  describe('1. 真实 locale 文件加载验证', () => {
    it('zh-CN 应能正常导入且为对象', () => {
      expect(zhCN).toBeDefined()
      expect(typeof zhCN).toBe('object')
      expect(zhCN).not.toBeNull()
    })

    it('en-US 应能正常导入且为对象', () => {
      expect(enUS).toBeDefined()
      expect(typeof enUS).toBe('object')
      expect(enUS).not.toBeNull()
    })

    it('zh-CN 应至少包含 10 个顶级命名空间', () => {
      const topKeys = Object.keys(zhCNObj)
      expect(topKeys.length).toBeGreaterThanOrEqual(10)
    })

    it('en-US 顶级命名空间应与 zh-CN 完全一致', () => {
      const zhTop = Object.keys(zhCNObj).sort()
      const enTop = Object.keys(enUSObj).sort()
      expect(enTop).toEqual(zhTop)
    })
  })

  describe('2. 键结构一致性（核心：en-US 100% 覆盖）', () => {
    it('zh-CN 与 en-US 的键路径集合应完全一致', () => {
      expect(enKeyPaths).toEqual(zhKeyPaths)
    })

    it('zh-CN 键数量应 ≥ 60（确保语言包丰富度）', () => {
      expect(zhKeyPaths.length).toBeGreaterThanOrEqual(60)
    })

    it('en-US 键数量应与 zh-CN 相同', () => {
      expect(enKeyPaths.length).toBe(zhKeyPaths.length)
    })

    it('应不存在 en-US 缺失的键', () => {
      const missingInEn = zhKeyPaths.filter((k) => !enKeyPaths.includes(k))
      expect(missingInEn).toEqual([])
    })

    it('应不存在 zh-CN 缺失的键（避免 en-US 多余未使用键）', () => {
      const missingInZh = enKeyPaths.filter((k) => !zhKeyPaths.includes(k))
      expect(missingInZh).toEqual([])
    })

    it('每个键路径的值类型应一致（同为字符串或同为对象）', () => {
      const mismatches: string[] = []
      for (const path of zhKeyPaths) {
        const zhVal = getValueByPath(zhCNObj, path)
        const enVal = getValueByPath(enUSObj, path)
        if (typeof zhVal !== typeof enVal) {
          mismatches.push(`${path}: zh=${typeof zhVal}, en=${typeof enVal}`)
        }
      }
      expect(mismatches).toEqual([])
    })
  })

  describe('3. 键值非空验证', () => {
    it('所有 zh-CN 键值应非空（非空字符串、非 null、非 undefined）', () => {
      const empties: string[] = []
      for (const [path, value] of getEntries(zhCNObj)) {
        if (value === null || value === undefined || value === '') {
          empties.push(path)
        }
      }
      expect(empties).toEqual([])
    })

    it('所有 en-US 键值应非空（避免占位符或漏翻译）', () => {
      const empties: string[] = []
      for (const [path, value] of getEntries(enUSObj)) {
        if (value === null || value === undefined || value === '') {
          empties.push(path)
        }
      }
      expect(empties).toEqual([])
    })

    it('en-US 不应包含中文占位符（如 "TODO"、"待翻译"）', () => {
      const placeholders: string[] = []
      for (const [path, value] of getEntries(enUSObj)) {
        if (typeof value === 'string' && /^(TODO|待翻译|未翻译)$/i.test(value.trim())) {
          placeholders.push(path)
        }
      }
      expect(placeholders).toEqual([])
    })
  })

  describe('4. 翻译内容差异验证（防止未翻译直接复制）', () => {
    it('所有键路径的中英文值应不同（避免复制未翻译）', () => {
      const duplicates: string[] = []
      for (const path of zhKeyPaths) {
        const zhVal = getValueByPath(zhCNObj, path)
        const enVal = getValueByPath(enUSObj, path)
        // 跳过数字、布尔等非字符串值
        if (typeof zhVal === 'string' && typeof enVal === 'string') {
          // 跳过纯数字、纯符号、品牌名（如 'English'）
          if (/^[\d\s\W]+$/.test(zhVal)) continue
          if (zhVal === enVal && /[\u4e00-\u9fa5]/.test(zhVal)) {
            // 中文值与英文值相同且确实包含中文 → 未翻译
            duplicates.push(`${path}: "${zhVal}"`)
          }
        }
      }
      expect(duplicates).toEqual([])
    })

    it('zh-CN 文本应包含中文字符', () => {
      const chineseEntries = getEntries(zhCNObj).filter(
        ([, v]) => typeof v === 'string'
      )
      expect(chineseEntries.length).toBeGreaterThan(0)
      const hasChinese = chineseEntries.some(([, v]) =>
        /[\u4e00-\u9fa5]/.test(v as string)
      )
      expect(hasChinese).toBe(true)
    })

    it('en-US 文本应包含拉丁字母（非纯中文），仅允许 language.zh 例外', () => {
      const englishEntries = getEntries(enUSObj).filter(
        ([, v]) => typeof v === 'string'
      )
      expect(englishEntries.length).toBeGreaterThan(0)
      // 所有英文值应至少包含一个 ASCII 字母或数字
      // 例外：language.zh = '中文'（语言自名规范，英文环境下显示中文选项为中文）
      const nonLatin: string[] = []
      for (const [path, v] of englishEntries) {
        if (!/[a-zA-Z0-9]/.test(v as string)) {
          nonLatin.push(path)
        }
      }
      expect(nonLatin).toEqual(['language.zh'])
    })
  })

  describe('5. 命名规范验证', () => {
    it('所有键应使用 camelCase 命名', () => {
      const invalid: string[] = []
      for (const path of zhKeyPaths) {
        const parts = path.split('.')
        for (const part of parts) {
          // 允许：纯小写字母数字、camelCase（首字母小写后续大写）
          if (!/^[a-z][a-zA-Z0-9]*$/.test(part)) {
            invalid.push(`${path}（段：${part}）`)
          }
        }
      }
      expect(invalid).toEqual([])
    })

    it('顶级命名空间应使用小写单词', () => {
      const topKeys = Object.keys(zhCNObj)
      for (const key of topKeys) {
        expect(key).toMatch(/^[a-z][a-zA-Z]*$/)
      }
    })
  })

  describe('6. 命名空间覆盖性验证', () => {
    it('应包含核心命名空间 common', () => {
      expect(zhCNObj).toHaveProperty('common')
      expect(enUSObj).toHaveProperty('common')
    })

    it('应包含导航命名空间 nav', () => {
      expect(zhCNObj).toHaveProperty('nav')
      expect(enUSObj).toHaveProperty('nav')
    })

    it('应包含布局命名空间 layout', () => {
      expect(zhCNObj).toHaveProperty('layout')
      expect(enUSObj).toHaveProperty('layout')
    })

    it('应包含角色命名空间 role', () => {
      expect(zhCNObj).toHaveProperty('role')
      expect(enUSObj).toHaveProperty('role')
    })

    it('应包含用户命名空间 user', () => {
      expect(zhCNObj).toHaveProperty('user')
      expect(enUSObj).toHaveProperty('user')
    })

    it('应包含主题命名空间 theme', () => {
      expect(zhCNObj).toHaveProperty('theme')
      expect(enUSObj).toHaveProperty('theme')
    })

    it('应包含语言命名空间 language', () => {
      expect(zhCNObj).toHaveProperty('language')
      expect(enUSObj).toHaveProperty('language')
    })

    it('应包含监控命名空间 monitoring', () => {
      expect(zhCNObj).toHaveProperty('monitoring')
      expect(enUSObj).toHaveProperty('monitoring')
    })

    it('应包含报告命名空间 report', () => {
      expect(zhCNObj).toHaveProperty('report')
      expect(enUSObj).toHaveProperty('report')
    })

    it('应包含错误命名空间 error', () => {
      expect(zhCNObj).toHaveProperty('error')
      expect(enUSObj).toHaveProperty('error')
    })
  })

  describe('7. 关键翻译键抽样验证', () => {
    it('layout.appTitle 应有正确翻译', () => {
      expect(zhCNObj.layout?.appTitle).toBe('心理预警平台')
      expect(enUSObj.layout?.appTitle).toBe('Mental Health Alert Platform')
    })

    it('role.admin/counselor/user 应有正确翻译', () => {
      expect(zhCNObj.role?.admin).toBe('管理员')
      expect(enUSObj.role?.admin).toBe('Administrator')
      expect(zhCNObj.role?.counselor).toBe('咨询师')
      expect(enUSObj.role?.counselor).toBe('Counselor')
      expect(zhCNObj.role?.user).toBe('普通用户')
      expect(enUSObj.role?.user).toBe('User')
    })

    it('monitoring.alertLevel 应有 4 个等级翻译', () => {
      const zhLevels = (zhCNObj.monitoring as StringDict).alertLevel as StringDict
      const enLevels = (enUSObj.monitoring as StringDict).alertLevel as StringDict
      expect(Object.keys(zhLevels).sort()).toEqual(['critical', 'high', 'low', 'medium'])
      expect(Object.keys(enLevels).sort()).toEqual(['critical', 'high', 'low', 'medium'])
      expect(zhLevels.critical).toBe('严重')
      expect(enLevels.critical).toBe('Critical')
    })

    it('report.exportStatus 应有 4 个状态翻译', () => {
      const zhStatus = (zhCNObj.report as StringDict).exportStatus as StringDict
      const enStatus = (enUSObj.report as StringDict).exportStatus as StringDict
      expect(Object.keys(zhStatus).sort()).toEqual(['completed', 'failed', 'pending', 'processing'])
      expect(Object.keys(enStatus).sort()).toEqual(['completed', 'failed', 'pending', 'processing'])
    })

    it('language.zh/en 应正确反映自身语言名', () => {
      expect(zhCNObj.language?.zh).toBe('中文')
      expect(enUSObj.language?.en).toBe('English')
    })

    it('layout.warningNotificationTitle/Message 应存在（M-FE-5 修复键）', () => {
      expect(zhCNObj.layout?.warningNotificationTitle).toBeDefined()
      expect(enUSObj.layout?.warningNotificationTitle).toBeDefined()
      expect(zhCNObj.layout?.warningNotificationMessage).toBeDefined()
      expect(enUSObj.layout?.warningNotificationMessage).toBeDefined()
    })
  })

  describe('8. 占位符参数验证', () => {
    it('包含 {level} 占位符的翻译键应同步存在', () => {
      const zhMsg = zhCNObj.layout?.warningNotificationMessage as string | undefined
      const enMsg = enUSObj.layout?.warningNotificationMessage as string | undefined
      expect(zhMsg).toContain('{level}')
      expect(enMsg).toContain('{level}')
    })
  })
})

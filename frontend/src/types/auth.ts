/**
 * 认证相关公共类型定义。
 *
 * 提取自 `@/api/auth` 以打破 `utils/authStorage.ts` 与 `api/auth.ts` 之间的类型-only 循环依赖：
 * 原先 `authStorage.ts` 通过 `import type { UserInfo } from '@/api/auth'` 引用类型，
 * 而 `api/auth.ts -> api/request.ts -> utils/authStorage.ts` 形成运行时链路，
 * 导致静态分析工具（madge）误报循环依赖。
 *
 * 现将 `UserInfo` 类型下沉到无依赖的 `types/` 目录，由 `api/auth.ts` 再导出以保持公共 API 向后兼容。
 */
export interface UserInfo {
  id: number
  username: string
  role: 'user' | 'counselor' | 'admin'
  nickname?: string
  email?: string
}

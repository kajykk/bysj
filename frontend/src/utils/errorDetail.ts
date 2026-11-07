import { normalizeHttpErrorInfo } from '@/utils/httpError'

// L-15：错误 detail 提取统一委托给 normalizeHttpErrorInfo（含 userMessage、
// 状态码映射与 httpError 的安全过滤），本文件只保留一处逻辑，避免规则漂移。
export const getErrorDetail = (error: unknown, fallback: string): string =>
  normalizeHttpErrorInfo(error, fallback).detail

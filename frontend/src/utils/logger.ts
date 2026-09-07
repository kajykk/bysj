/**
 * N4: 统一前端日志出口。
 *
 * 背景：vite 生产构建 `esbuild.drop: ['console']` 会移除所有 console.* 调用，
 * 导致 fire-and-forget 失败信号（token 刷新失败、请求拦截器错误日志、
 * 性能上报失败等）在生产环境完全消失——连 Sentry 都收不到，形成观测盲区。
 *
 * 策略：
 * - 开发/测试环境：透传 console（保持既有调试体验与测试 spy 兼容）
 * - 生产环境：路由到 Sentry capture（captureMessage / captureException 不是
 *   console 调用，不会被 esbuild drop），确保失败可观测
 * - error 级别：优先提取 args 中的 Error 实例作为异常对象；其余参数结构化
 *   挂到 Sentry extra（message + args），避免非 Error 关键信息（如 URL、状态码）
 *   在包装成 Error 后丢失可读性
 *
 * 注意：本模块不得反向依赖 request.ts / router（避免循环依赖，
 * 与 request.ts 中 "循环依赖治理" 的约束一致）。
 */
import { captureException, captureMessage } from '@/plugins/sentry'

const IS_PROD = import.meta.env.PROD

type LoggerLevel = 'info' | 'warn' | 'error'

function emit(level: LoggerLevel, message: string, ...args: unknown[]): void {
  if (!IS_PROD) {
    const fn =
      level === 'error' ? console.error : level === 'warn' ? console.warn : console.info
    fn(message, ...args)
    return
  }
  // 生产：console.* 已被 esbuild drop，改走 Sentry 保持可观测
  if (level === 'error') {
    const rawError = args.find((arg) => arg instanceof Error)
    const err = rawError instanceof Error ? rawError : new Error(message)
    const extraArgs = args.filter((arg) => arg !== rawError)
    captureException(err, { message, args: extraArgs })
  } else {
    // Sentry SeverityLevel 使用 'warning' 而非 'warn'
    const severity = level === 'warn' ? 'warning' : 'info'
    captureMessage(`[${level.toUpperCase()}] ${message}`, severity)
  }
}

export const logger = {
  info: (message: string, ...args: unknown[]): void => emit('info', message, ...args),
  warn: (message: string, ...args: unknown[]): void => emit('warn', message, ...args),
  error: (message: string, ...args: unknown[]): void => emit('error', message, ...args),
}

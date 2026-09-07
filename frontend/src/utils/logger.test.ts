/**
 * N4: logger 统一出口单元测试。
 *
 * 策略验证：
 * - 非生产环境（vitest 中 import.meta.env.PROD === false）：透传 console.*，
 *   保持开发体验 + 测试 spy 兼容
 * - 生产分支（Sentry 路由）由 plugins/sentry.test.ts 覆盖 capture 契约
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { logger } from './logger'

describe('logger', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('非生产环境 warn 透传 console.warn', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    logger.warn('boom', 'detail')
    expect(spy).toHaveBeenCalledWith('boom', 'detail')
    spy.mockRestore()
  })

  it('非生产环境 error 透传 console.error', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const err = new Error('x')
    logger.error('oops', err)
    expect(spy).toHaveBeenCalledWith('oops', err)
    spy.mockRestore()
  })

  it('非生产环境 info 透传 console.info', () => {
    const spy = vi.spyOn(console, 'info').mockImplementation(() => {})
    logger.info('hello')
    expect(spy).toHaveBeenCalledWith('hello')
    spy.mockRestore()
  })

  it('logger 对象结构稳定（info/warn/error）', () => {
    expect(typeof logger.info).toBe('function')
    expect(typeof logger.warn).toBe('function')
    expect(typeof logger.error).toBe('function')
  })

  it('error 级别保留 message 与全部 args 透传（结构化上下文不丢失）', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const detail = { status: 500, url: '/api/v1/x' }
    logger.error('request failed', detail)
    expect(spy).toHaveBeenCalledWith('request failed', detail)
    spy.mockRestore()
  })

  it('error 级别首个参数为 Error 时仍透传后续上下文参数', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const err = new Error('boom')
    logger.error('service failed', err, 'ctx-1')
    expect(spy).toHaveBeenCalledWith('service failed', err, 'ctx-1')
    spy.mockRestore()
  })
})

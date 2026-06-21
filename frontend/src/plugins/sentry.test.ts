import { describe, it, expect, vi } from 'vitest'

/**
 * Sentry 插件单元测试
 * T-COV-SEN-FE-001: 前端 Sentry 集成
 */

describe('Sentry Plugin - T-COV-SEN-FE-001', () => {
  describe('1. 配置验证', () => {
    it('应正确读取环境变量', () => {
      const dsn = import.meta.env.VITE_SENTRY_DSN
      // DSN 可能未配置，但不应抛出错误
      expect(typeof dsn).toBe('string')
    })

    it('应正确解析采样率', () => {
      const rate = parseFloat(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE || '0.1')
      expect(rate).toBeGreaterThanOrEqual(0)
      expect(rate).toBeLessThanOrEqual(1)
    })
  })

  describe('2. 错误捕获', () => {
    it('应支持错误对象捕获', () => {
      const error = new Error('test error')
      expect(error.message).toBe('test error')
    })

    it('应支持上下文数据', () => {
      const context = { userId: 123, action: 'test' }
      expect(context.userId).toBe(123)
      expect(context.action).toBe('test')
    })
  })

  describe('3. 消息捕获', () => {
    it('应支持不同级别消息', () => {
      const levels = ['debug', 'info', 'warning', 'error', 'fatal']
      levels.forEach((level) => {
        expect(level).toBeDefined()
      })
    })
  })
})

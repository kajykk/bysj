import { describe, expect, it } from 'vitest'
import { DEV_POLICY, PROD_POLICY } from './csp'

/**
 * CSP unsafe-eval 加固的回归锁。
 *
 * 本轮（2026-10-08）移除 'unsafe-eval' 的依据是实测，不是推测：
 *   - 静态：dist/assets 全量 chunk 中 `new Function` / 裸 `eval(` / `Function('` 0 命中
 *   - 动态：真实 Chromium 遍历 19 条登录后路由（ECharts 实际渲染出 canvas）A/B 对比，
 *     去掉 'unsafe-eval' 后 securitypolicyviolation 0 条，渲染与基线逐字符一致
 *   - 捕获器有效性经正向对照验证（主动 eval 可稳定抓到 blockedURI=eval）
 *
 * 这里断言的是**策略产物本身**（导出常量），不解析源码字面，避免注释改动误伤。
 */
function scriptSrcSegment(policy: string): string {
  const parts = policy.split('script-src')
  return parts.length > 1 ? parts[1].split(';')[0].trim() : ''
}

describe('csp: script-src 不含 unsafe-eval', () => {
  it('生产策略不含 unsafe-eval', () => {
    expect(PROD_POLICY).not.toContain('unsafe-eval')
  })

  it('开发策略不含 unsafe-eval（与生产一致，便于本地暴露 eval 回归）', () => {
    expect(DEV_POLICY).not.toContain('unsafe-eval')
  })

  it('生产 script-src 段仅包含 self', () => {
    expect(scriptSrcSegment(PROD_POLICY)).toBe("'self'")
  })

  it('开发 script-src 段仅包含 self', () => {
    expect(scriptSrcSegment(DEV_POLICY)).toBe("'self'")
  })

  it('两档 script-src 都不含 unsafe-inline（XSS 防线不后退）', () => {
    expect(scriptSrcSegment(PROD_POLICY)).not.toContain('unsafe-inline')
    expect(scriptSrcSegment(DEV_POLICY)).not.toContain('unsafe-inline')
  })

  it('两档 script-src 都不放行通配符或 data:（不引入新的脚本入口）', () => {
    for (const seg of [scriptSrcSegment(PROD_POLICY), scriptSrcSegment(DEV_POLICY)]) {
      expect(seg).not.toContain('*')
      expect(seg).not.toContain('data:')
    }
  })
})

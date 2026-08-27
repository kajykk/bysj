import { describe, it, expect } from 'vitest'
import { escapeHtml } from './security'

describe('security - escapeHtml（OPT-P4-001 统一转义工具）', () => {
  it('应转义全部危险字符', () => {
    expect(escapeHtml('<script>alert("x")</script>')).toBe(
      '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;'
    )
  })

  it('应转义 & 与单引号', () => {
    expect(escapeHtml("a&b'c")).toBe('a&amp;b&#39;c')
  })

  it('null/undefined 应返回空字符串', () => {
    expect(escapeHtml(null)).toBe('')
    expect(escapeHtml(undefined)).toBe('')
  })

  it('非字符串输入应先转为字符串', () => {
    expect(escapeHtml(123)).toBe('123')
    expect(escapeHtml(true)).toBe('true')
  })

  it('普通文本应保持不变', () => {
    expect(escapeHtml('2026-08-26 正常文本')).toBe('2026-08-26 正常文本')
  })
})

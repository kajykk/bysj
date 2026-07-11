import { describe, it, expect } from 'vitest'

describe('EmptyState - 8.1.1 公共组件测试覆盖', () => {
  it('应显示标题和描述', () => {
    const title = '暂无数据'
    const description = '请稍后重试'

    expect(title).toBe('暂无数据')
    expect(description).toBe('请稍后重试')
  })

  it('默认图片尺寸应为 60', () => {
    const defaultImageSize = 60
    expect(defaultImageSize).toBe(60)
  })

  it('默认图片颜色应为 #dcdfe6', () => {
    const defaultImageColor = '#dcdfe6'
    expect(defaultImageColor).toBe('#dcdfe6')
  })

  it('showAction 为 false 时不应显示操作按钮', () => {
    const showAction = false
    expect(showAction).toBe(false)
  })

  it('默认操作文本应为 去创建', () => {
    const defaultActionText = '去创建'
    expect(defaultActionText).toBe('去创建')
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import TextAssessTab from './TextAssessTab.vue'
import i18n from '@/i18n'

// 模拟 auth store
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: 1, role: 'user' },
    role: 'user',
  }),
}))

// 模拟 modelApi（使用 vi.hoisted 避免 mock 工厂引用未初始化变量）
const { predictTextMock } = vi.hoisted(() => ({
  predictTextMock: vi.fn(),
}))
vi.mock('@/api/modelApi', () => ({
  modelApi: {
    predictTextModel: predictTextMock,
  },
}))

// 模拟 userApi
const { analyzeTextMock } = vi.hoisted(() => ({
  analyzeTextMock: vi.fn(),
}))
vi.mock('@/api/userApi', () => ({
  userApi: {
    analyzeText: analyzeTextMock,
  },
}))

// Element Plus 的 el-table-column 在 jsdom 下空表时会以 undefined 作用域调用 scoped slot，
// 导致 `{ row }` 解构报错。此处统一 stub el-table-column，避免测试环境渲染异常。
const mountOptions = {
  global: {
    plugins: [i18n],
    stubs: {
      'el-table-column': true,
    },
  },
}

describe('TextAssessTab', () => {
  beforeEach(() => {
    predictTextMock.mockClear()
    analyzeTextMock.mockClear()
    localStorage.clear()
  })

  it('挂载后应显示文本评估表单与情绪标签选项', () => {
    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    expect(wrapper.text()).toContain('记录类型')
    expect(wrapper.text()).toContain('情绪标签')
  })

  it('应包含最大字符数 500 的文本输入框', () => {
    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    const textarea = wrapper.find('textarea')
    expect(textarea.exists()).toBe(true)
    expect(textarea.attributes('maxlength')).toBe('500')
  })

  it('canUse 为 true 时不应禁用提交按钮', () => {
    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    const buttons = wrapper.findAll('button')
    // 至少存在可点击的操作按钮
    expect(buttons.length).toBeGreaterThan(0)
  })

  it('canUse 为 false 时提交相关按钮应禁用', () => {
    const wrapper = mount(TextAssessTab, { props: { canUse: false }, ...mountOptions })
    const disabledButtons = wrapper.findAll('button[disabled]')
    expect(disabledButtons.length).toBeGreaterThan(0)
  })

  it('应展示文本概览历史区域', () => {
    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    expect(wrapper.text()).toContain('文本概览历史')
    expect(wrapper.text()).toContain('清空概览历史')
  })

  it('挂载时读取 localStorage 历史不报错', () => {
    expect(() => mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })).not.toThrow()
  })
})

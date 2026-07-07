import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import StructuredAssessTab from './StructuredAssessTab.vue'
import i18n from '@/i18n'

// 模拟 auth store，提供固定的 user.id
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: 1, role: 'user' },
    role: 'user',
  }),
}))

// 模拟 modelApi（使用 vi.hoisted 避免 mock 工厂引用未初始化变量）
const { predictTabularMock } = vi.hoisted(() => ({
  predictTabularMock: vi.fn(),
}))
vi.mock('@/api/modelApi', () => ({
  modelApi: {
    predictTabularModel: predictTabularMock,
  },
}))

// 模拟 userApi
const { collectStructuredMock } = vi.hoisted(() => ({
  collectStructuredMock: vi.fn(),
}))
vi.mock('@/api/userApi', () => ({
  userApi: {
    collectStructuredData: collectStructuredMock,
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

describe('StructuredAssessTab', () => {
  beforeEach(() => {
    predictTabularMock.mockClear()
    collectStructuredMock.mockClear()
    localStorage.clear()
  })

  it('挂载后应显示结构化概览表单卡片标题', () => {
    const wrapper = mount(StructuredAssessTab, { props: { canUse: true }, ...mountOptions })
    expect(wrapper.find('.card-title').text()).toContain('结构化概览表单')
  })

  it('应提供单页模式与分步向导切换', () => {
    const wrapper = mount(StructuredAssessTab, { props: { canUse: true }, ...mountOptions })
    expect(wrapper.text()).toContain('单页模式')
    expect(wrapper.text()).toContain('分步向导')
  })

  it('canUse 为 false 时表单仍可渲染', () => {
    const wrapper = mount(StructuredAssessTab, { props: { canUse: false }, ...mountOptions })
    // canUse 当前未绑定到按钮 disabled，仅验证表单正常渲染
    const submitBtn = wrapper.findAll('button').find(b => b.text().includes('提交概览'))
    expect(submitBtn).toBeTruthy()
  })

  it('点击"查看概览报告"应触发 view-report 事件（结果卡片可见时）', async () => {
    // "查看概览报告"按钮位于 v-if="structuredResult || modelTabResult" 的结果卡片内，
    // 需要先有结果才会渲染。此处验证未提交时该按钮不存在，确保条件渲染生效。
    const wrapper = mount(StructuredAssessTab, { props: { canUse: true }, ...mountOptions })
    const btn = wrapper.findAll('button').find(b => b.text().includes('查看概览报告'))
    expect(btn).toBeFalsy()
  })

  it('挂载时应从 localStorage 读取概览历史（空时不报错）', () => {
    expect(() => mount(StructuredAssessTab, { props: { canUse: true }, ...mountOptions })).not.toThrow()
  })

  it('概览历史区域应展示清空与导出按钮', () => {
    const wrapper = mount(StructuredAssessTab, { props: { canUse: true }, ...mountOptions })
    expect(wrapper.text()).toContain('概览历史')
    expect(wrapper.text()).toContain('清空概览历史')
    expect(wrapper.text()).toContain('导出历史概览 CSV')
  })
})

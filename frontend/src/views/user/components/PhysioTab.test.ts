import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PhysioTab from './PhysioTab.vue'
import i18n from '@/i18n'

// 模拟 auth store，提供固定的 user.id
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: 1, role: 'user' },
    role: 'user',
  }),
}))

// 模拟 userApi（使用 vi.hoisted 避免 mock 工厂引用未初始化变量）
const { recordPhysiologicalMock } = vi.hoisted(() => ({
  recordPhysiologicalMock: vi.fn(),
}))
vi.mock('@/api/userApi', () => ({
  userApi: {
    recordPhysiological: recordPhysiologicalMock,
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

describe('PhysioTab', () => {
  beforeEach(() => {
    recordPhysiologicalMock.mockClear()
    localStorage.clear()
  })

  it('挂载后应显示生理概览表单与数据来源选项', () => {
    const wrapper = mount(PhysioTab, { props: { canUse: true }, ...mountOptions })
    expect(wrapper.text()).toContain('数据来源')
    // el-select 下拉选项在未展开时不会渲染到文本中，改为验证 select 元素存在
    expect(wrapper.find('.el-select').exists()).toBe(true)
  })

  it('应展示各字段合理性提示', () => {
    const wrapper = mount(PhysioTab, { props: { canUse: true }, ...mountOptions })
    expect(wrapper.text()).toContain('成年人建议 7-9 小时')
    expect(wrapper.text()).toContain('正常静息心率 60-100 bpm')
    expect(wrapper.text()).toContain('建议每日 8000-10000 步')
  })

  it('canUse 为 true 时提交按钮不应禁用', () => {
    const wrapper = mount(PhysioTab, { props: { canUse: true }, ...mountOptions })
    const submitBtn = wrapper.findAll('button').find(b => b.text().includes('提交记录'))
    expect(submitBtn).toBeTruthy()
    expect(submitBtn!.attributes('disabled')).toBeUndefined()
  })

  it('canUse 为 false 时提交按钮应禁用', () => {
    const wrapper = mount(PhysioTab, { props: { canUse: false }, ...mountOptions })
    const submitBtn = wrapper.findAll('button').find(b => b.text().includes('提交记录'))
    expect(submitBtn).toBeTruthy()
    expect(submitBtn!.attributes('disabled')).toBeDefined()
  })

  it('应展示生理概览历史区域及清空、导出按钮', () => {
    const wrapper = mount(PhysioTab, { props: { canUse: true }, ...mountOptions })
    expect(wrapper.text()).toContain('生理概览历史')
    expect(wrapper.text()).toContain('导出生理概览 CSV')
    expect(wrapper.text()).toContain('清空概览历史')
  })

  it('无历史记录时应显示空状态占位', () => {
    const wrapper = mount(PhysioTab, { props: { canUse: true }, ...mountOptions })
    expect(wrapper.text()).toContain('暂无生理概览历史')
  })

  it('挂载时读取 localStorage 历史不报错', () => {
    expect(() => mount(PhysioTab, { props: { canUse: true }, ...mountOptions })).not.toThrow()
  })

  it('点击清空按钮应清空历史并显示空状态', async () => {
    const wrapper = mount(PhysioTab, { props: { canUse: true }, ...mountOptions })
    const clearBtn = wrapper.findAll('button').find(b => b.text().includes('清空概览历史'))
    expect(clearBtn).toBeTruthy()
    await clearBtn!.trigger('click')
    // 清空后仍应显示空状态
    expect(wrapper.text()).toContain('暂无生理概览历史')
  })

  it('提交生理数据应调用 recordPhysiological 接口并触发 submitted 事件', async () => {
    recordPhysiologicalMock.mockResolvedValue({})
    const wrapper = mount(PhysioTab, { props: { canUse: true }, ...mountOptions })
    const submitBtn = wrapper.findAll('button').find(b => b.text().includes('提交记录'))
    expect(submitBtn).toBeTruthy()
    await submitBtn!.trigger('click')
    await flushPromises()
    expect(recordPhysiologicalMock).toHaveBeenCalled()
    const emitted = wrapper.emitted('submitted')
    expect(emitted).toBeTruthy()
    const payload = emitted![0][0] as { physiologicalJson: string; physioFormData: Record<string, unknown> }
    expect(payload.physiologicalJson).toBeTruthy()
    const parsed = JSON.parse(payload.physiologicalJson)
    expect(parsed.sleep_hours).toBeDefined()
    expect(parsed.heart_rate).toBeDefined()
    expect(parsed.steps).toBeDefined()
    expect(payload.physioFormData).toBeDefined()
  })

  it('提交失败应不触发 submitted 事件', async () => {
    recordPhysiologicalMock.mockRejectedValue(new Error('网络错误'))
    const wrapper = mount(PhysioTab, { props: { canUse: true }, ...mountOptions })
    const submitBtn = wrapper.findAll('button').find(b => b.text().includes('提交记录'))
    await submitBtn!.trigger('click')
    await flushPromises()
    expect(wrapper.emitted('submitted')).toBeFalsy()
  })
})

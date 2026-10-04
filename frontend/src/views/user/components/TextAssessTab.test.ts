import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
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
const { analyzeTextMock, saveDraftMock, getDraftMock } = vi.hoisted(() => ({
  analyzeTextMock: vi.fn(),
  saveDraftMock: vi.fn(),
  getDraftMock: vi.fn(),
}))
vi.mock('@/api/userApi', () => ({
  userApi: {
    analyzeText: analyzeTextMock,
    saveDraft: saveDraftMock,
    getDraft: getDraftMock,
  },
}))

// 模拟 element-plus 的消息组件（草稿恢复流程需要拦截 ElMessageBox.confirm，
// 否则 jsdom 下真实对话框会挂起等待交互；模板中的 el-* 组件走原生 fallback 不受影响）
const { messageSuccessMock, messageErrorMock, messageWarningMock, messageBoxConfirmMock } = vi.hoisted(() => ({
  messageSuccessMock: vi.fn(),
  messageErrorMock: vi.fn(),
  messageWarningMock: vi.fn(),
  messageBoxConfirmMock: vi.fn(),
}))
// 部分模拟 element-plus：保留全部组件导出（模板 auto-import 需要 ElOption 等），
// 仅覆盖 ElMessage / ElMessageBox——草稿恢复流程需要拦截 confirm，
// 否则 jsdom 下真实对话框会挂起等待交互
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: {
      success: messageSuccessMock,
      error: messageErrorMock,
      warning: messageWarningMock,
    },
    ElMessageBox: {
      confirm: messageBoxConfirmMock,
    },
  }
})

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
    saveDraftMock.mockClear()
    getDraftMock.mockReset()
    messageSuccessMock.mockClear()
    messageErrorMock.mockClear()
    messageWarningMock.mockClear()
    messageBoxConfirmMock.mockReset()
    // 默认无草稿、用户确认恢复，避免用例间相互污染
    getDraftMock.mockResolvedValue(null)
    messageBoxConfirmMock.mockResolvedValue(true)
    saveDraftMock.mockResolvedValue({ draft_id: 1 })
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

  // ── AUDIT-2026-10-01（决策三 P6）：草稿保存与恢复 ──
  it('保存草稿按钮存在且内容为空时禁用', () => {
    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    const saveBtn = wrapper.findAll('button').find(b => b.text().includes('保存草稿'))
    expect(saveBtn).toBeDefined()
    expect(saveBtn!.attributes('disabled')).toBeDefined()
  })

  it('填入内容点击保存草稿 → 以 text_assessment 类型调用 saveDraft', async () => {
    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('今天心情不太好，写一半')
    const saveBtn = wrapper.findAll('button').find(b => b.text().includes('保存草稿'))
    await saveBtn!.trigger('click')
    await flushPromises()

    expect(saveDraftMock).toHaveBeenCalledTimes(1)
    expect(saveDraftMock).toHaveBeenCalledWith('text_assessment', expect.objectContaining({
      content: '今天心情不太好，写一半',
      entry_type: 'diary'
    }))
    expect(messageSuccessMock).toHaveBeenCalled()
  })

  it('挂载时发现草稿且用户确认 → 表单恢复草稿内容', async () => {
    getDraftMock.mockResolvedValue({
      draft_id: 3,
      data_payload: { entry_type: 'vent', content: '恢复的草稿内容', emotion_tags: ['anxiety'], mood_score: 2 }
    })
    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await flushPromises()

    expect(messageBoxConfirmMock).toHaveBeenCalledTimes(1)
    const textarea = wrapper.find('textarea')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('恢复的草稿内容')
    expect(messageSuccessMock).toHaveBeenCalled()
  })

  it('挂载时发现草稿但用户放弃 → 不恢复且用空内容覆盖后端草稿', async () => {
    getDraftMock.mockResolvedValue({
      draft_id: 3,
      data_payload: { entry_type: 'diary', content: '不想恢复的内容' }
    })
    messageBoxConfirmMock.mockRejectedValue(new Error('cancel'))
    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await flushPromises()

    const textarea = wrapper.find('textarea')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
    // 放弃后以空 content 覆盖草稿，避免下次重复询问
    expect(saveDraftMock).toHaveBeenCalledWith('text_assessment', expect.objectContaining({ content: '' }))
    expect(messageSuccessMock).not.toHaveBeenCalled()
  })

  it('挂载时无草稿（404→null）→ 不弹恢复确认', async () => {
    const wrapper = mount(TextAssessTab, { props: { canUse: true }, ...mountOptions })
    await flushPromises()

    expect(messageBoxConfirmMock).not.toHaveBeenCalled()
    expect(wrapper.find('textarea').exists()).toBe(true)
  })
})

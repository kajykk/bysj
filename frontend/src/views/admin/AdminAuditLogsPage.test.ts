import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AdminAuditLogsPage from './AdminAuditLogsPage.vue'
import i18n from '@/i18n'

// 模拟 auth store（页面用 auth.role 判断审计明细权限）
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: 1, role: 'admin' },
    role: 'admin',
  }),
}))

// 模拟 useListQueryState：页面依赖其 page/pageSize/getString/setQuery（内部依赖 vue-router）
const { setQueryMock } = vi.hoisted(() => ({
  setQueryMock: vi.fn(),
}))
vi.mock('@/composables/useListQueryState', () => ({
  useListQueryState: () => ({
    page: { value: 1 },
    pageSize: { value: 50 },
    getString: (_key: string) => '',
    setQuery: setQueryMock,
  }),
}))

// 模拟 adminApi
const { listAuditLogsMock } = vi.hoisted(() => ({
  listAuditLogsMock: vi.fn(),
}))
vi.mock('@/api/adminApi', () => ({
  adminApi: {
    listAuditLogs: listAuditLogsMock,
  },
}))

// 部分模拟 element-plus：保留组件导出，仅拦截消息组件。
// 注意：showHttpFeedback 走子路径 'element-plus/es/components/message/index' 导入，
// 必须连子路径一并 mock，否则加载失败用例拦截不到提示。
// stub 需放 vi.hoisted（vi.mock 工厂被提升，普通 const 尚未初始化）
const { messageSuccessMock, messageErrorMock, messageWarningMock, elementPlusMessageStub } = vi.hoisted(() => {
  const stub = {
    ElMessage: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
  }
  return {
    messageSuccessMock: stub.ElMessage.success,
    messageErrorMock: stub.ElMessage.error,
    messageWarningMock: stub.ElMessage.warning,
    elementPlusMessageStub: stub,
  }
})
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return { ...actual, ...elementPlusMessageStub }
})
vi.mock('element-plus/es/components/message/index', () => elementPlusMessageStub)

const makeAuditResult = () => ({
  items: [
    { id: 1, operator_id: 2, operator_role: 'admin', action_type: 'user_file_upload', target_type: 'user_upload', target_id: 2, detail: null, ip_address: '127.0.0.1', created_at: '2026-10-01T10:00:00' }
  ],
  total: 1,
  page: 1,
  page_size: 50,
  compliance: {
    action_breakdown: { user_file_upload: 3, login: 2, warning_handle: 1 },
    earliest_log: '2026-07-03T00:00:00',
    latest_log: '2026-10-01T10:00:00',
    retention_days: 90
  }
})

const mountOptions = {
  global: {
    plugins: [i18n],
    stubs: {
      // 与 TextAssessTab.test.ts 同因：jsdom 下空表 scoped slot 以 undefined 作用域调用
      'el-table-column': true,
    },
  },
}

describe('AdminAuditLogsPage（AUDIT-2026-10-01 决策三 P2）', () => {
  beforeEach(() => {
    listAuditLogsMock.mockReset()
    setQueryMock.mockReset()
    listAuditLogsMock.mockResolvedValue(makeAuditResult())
    setQueryMock.mockResolvedValue(undefined)
    messageSuccessMock.mockClear()
    messageErrorMock.mockClear()
    messageWarningMock.mockClear()
  })

  it('挂载即加载审计日志（默认 page_size=50）并渲染合规统计条', async () => {
    const wrapper = mount(AdminAuditLogsPage, mountOptions)
    await flushPromises()

    expect(listAuditLogsMock).toHaveBeenCalledTimes(1)
    expect(listAuditLogsMock).toHaveBeenCalledWith(expect.objectContaining({
      page: 1,
      page_size: 50,
      action_types: undefined
    }))
    // 统计条：保留天数 / 时间窗 / 分布标签
    expect(wrapper.text()).toContain('合规审计日志')
    expect(wrapper.text()).toContain('90')
    expect(wrapper.text()).toContain('user_file_upload · 3')
    expect(wrapper.text()).toContain('login · 2')
  })

  it('分布超过 8 类时截断并提示剩余数量', async () => {
    const breakdown: Record<string, number> = {}
    for (let i = 1; i <= 11; i++) breakdown[`action_${i}`] = 12 - i
    listAuditLogsMock.mockResolvedValue({ ...makeAuditResult(), compliance: { ...makeAuditResult().compliance, action_breakdown: breakdown } })
    const wrapper = mount(AdminAuditLogsPage, mountOptions)
    await flushPromises()

    expect(wrapper.text()).toContain('action_1 · 11')
    expect(wrapper.text()).not.toContain('action_9 · 3')
    expect(wrapper.text()).toContain('另有 3 类')
  })

  it('加载失败时展示错误态并可重试', async () => {
    listAuditLogsMock.mockRejectedValueOnce({ response: { status: 500, data: { detail: '服务器错误' } } })
    const wrapper = mount(AdminAuditLogsPage, mountOptions)
    await flushPromises()

    expect(messageErrorMock).toHaveBeenCalled()
    // 重试：ListPageScaffold 把 retry 透传给 StatefulContainer，此处直接验证二次调用成功
    listAuditLogsMock.mockResolvedValueOnce(makeAuditResult())
    await (wrapper.vm as unknown as { fetchData: () => Promise<void> }).fetchData()
    await flushPromises()
    expect(listAuditLogsMock).toHaveBeenCalledTimes(2)
    expect(wrapper.vm.compliance).toBeTruthy()
  })

  it('compliance 为后端响应中的统计块（非分页字段）', async () => {
    const wrapper = mount(AdminAuditLogsPage, mountOptions)
    await flushPromises()
    const compliance = (wrapper.vm as unknown as { compliance: { retention_days: number } }).compliance
    expect(compliance.retention_days).toBe(90)
    expect(compliance.action_breakdown).toEqual({ user_file_upload: 3, login: 2, warning_handle: 1 })
  })
})

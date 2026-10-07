/**
 * UserAssessmentsPage 表格契约回归测试（FIX-2026-10-08）。
 *
 * 缺陷: 列表数据源是 `GET /user/data/history` → `DataHistoryItem { id, type,
 *       created_at, data }`（后端字面量见 backend/app/services/user_data_service.py
 *       :371-384 / 408-422 / 448-464），而表格 6 个 el-table-column 用的 prop 是
 *       `assessment_type` / `score` / `risk_level` / `summary` —— 后三项在该契约里
 *       不存在、`score` 也不在顶层，于是「得分 / 风险等级 / 摘要」三列**恒为空白**，
 *       用户看到一张只有 ID 和时间的表。
 *
 * 为什么既有测试没抓到: 这个页面此前没有任何挂载级测试，只有 i18n 键结构测试；
 *       纯函数测试也无从下手，因为取值规则全写在模板里。
 *
 * 断言方式: 用后端真实响应形状喂给 API mock，挂载真实组件，断言表格单元格里
 *       真的出现了得分 / 风险等级 / 摘要文本 —— 空白列会让这些断言全部失败。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'

const { historyMock } = vi.hoisted(() => ({ historyMock: vi.fn() }))

vi.mock('@/api/userApi', () => ({
  userApi: { getUserAssessmentHistory: historyMock },
}))

vi.mock('@/api/userRiskApi', () => ({
  userRiskApi: {},
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ role: 'user' }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), currentRoute: { value: { query: {} } } }),
}))

// el-table 在 jsdom 里需要 ResizeObserver
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub)

function makeHistoryResponse() {
  return {
    items: [
      {
        id: 11,
        type: 'structured',
        created_at: '2026-10-01T08:30:00',
        data: { assessment_type: 'PHQ-9', score: 72.5, severity: 'high', data_payload: {} },
      },
      {
        id: 12,
        type: 'text',
        created_at: '2026-10-02T09:00:00',
        data: {
          entry_type: 'diary',
          content: '最近两周睡眠很差',
          mood_score: 3,
          sentiment_score: 0.21,
        },
      },
      {
        id: 13,
        type: 'physiological',
        created_at: '2026-10-03T07:00:00',
        data: { source: 'wearable', sleep_hours: 5.5, steps: 4200 },
      },
    ],
    total: 3,
    page: 1,
    page_size: 10,
  }
}

const mountOptions = {
  global: {
    plugins: [i18n],
    stubs: { AssessmentsStatsCard: true },
  },
}

async function mountPage() {
  const wrapper = mount(
    await import('./UserAssessmentsPage.vue').then(m => m.default),
    mountOptions
  )
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('UserAssessmentsPage 表格契约', () => {
  beforeEach(() => {
    historyMock.mockReset()
    historyMock.mockResolvedValue(makeHistoryResponse())
  })

  it('得分列渲染 structured 的 data.score（改前取顶层 score → 恒空）', async () => {
    const wrapper = await mountPage()
    expect(wrapper.text()).toContain('72.5')
  })

  it('风险等级列渲染 structured 的 data.severity（改前取 risk_level → 恒空）', async () => {
    const wrapper = await mountPage()
    // severity='high' 经 severityLabel 翻译为「较高」；断言非空且不是占位符 '-'
    expect(wrapper.text()).toContain('较高')
    expect(wrapper.findAll('.el-table__row').length).toBe(3)
  })

  it('摘要列三类记录都有内容（改前取 summary → 恒空）', async () => {
    const wrapper = await mountPage()
    const text = wrapper.text()
    expect(text).toContain('PHQ-9')
    expect(text).toContain('最近两周睡眠很差')
    expect(text).toContain('睡眠 5.5h')
  })

  it('类型列三类都有标签（改前取 assessment_type → 恒空）', async () => {
    const wrapper = await mountPage()
    const text = wrapper.text()
    expect(text).toContain('结构化')
    expect(text).toContain('文本')
    expect(text).toContain('生理')
  })

  it('时间列渲染 created_at，不是空', async () => {
    const wrapper = await mountPage()
    expect(wrapper.text()).toMatch(/2026-10-0[123]/)
  })
})

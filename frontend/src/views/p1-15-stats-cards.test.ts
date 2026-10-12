/**
 * P1-15（F-03）第六轮前端闸门：9 个统计卡必须调后端 SQL 聚合端点。
 *
 * 缺陷背景（审查报告 F-03）：9 个 `*StatsCard.vue` 用 `page_size: 200`
 * 拉全量数据到前端 filter 做统计 —— 数据超窗口时分子截断、分母不截断，
 * 统计是错的。且实测（见后端 tests/api/test_p1_audit_2026_10_13_round6.py
 * 的 `test_old_frontend_approach_page_size_200_is_rejected`）：7 个列表端点
 * 的法定 `page_size` 上限是 100，旧前端发 200 直接被服务端 422 拒绝、
 * 被卡片空 catch 吞掉 → 这些统计卡**恒显示全 0**。
 *
 * 判据（行为级，不断言源码字面量）：
 * 1. 挂载后**只**调 stats 聚合方法（无参数），绝不调任何列表方法
 *    （列表 mock 零调用 = 不再拉全量）；
 * 2. 聚合响应的 snake_case 字段正确渲染进统计瓦片（全部非 0，
 *    证明值来自聚合响应而非初始默认值）；
 * 3. stats 抛错时卡片静默降级为 0 且不阻断（既有降级语义不回退）。
 *
 * 回退对照：把任一卡片改回「调列表端点 + 前端 filter」，对应用例必红
 * （列表 mock 被调用 + 渲染值非预期）。实测记录追记
 * docs/CODE_REVIEW_2026-10-11.md 第六轮。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AssessmentsStatsCard from '@/views/user/components/user-assessments/AssessmentsStatsCard.vue'
import CounselorWarningStatsCard from '@/views/counselor/components/counselor-warnings/CounselorWarningStatsCard.vue'
import UserOverviewStatsCard from '@/views/counselor/components/counselor-users/UserOverviewStatsCard.vue'
import CrisisEventStatsCard from '@/views/admin/components/admin-crisis-events/CrisisEventStatsCard.vue'
import AlertStatsCard from '@/views/admin/components/admin-alerts/AlertStatsCard.vue'
import SilenceStatsCard from '@/views/admin/components/admin-silences/SilenceStatsCard.vue'
import OperationLogStatsCard from '@/views/admin/components/admin-operation-logs/OperationLogStatsCard.vue'
import InterventionStatsCard from '@/views/user/components/user-intervention/InterventionStatsCard.vue'
import WarningStatsCard from '@/views/user/components/user-warnings/WarningStatsCard.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

vi.mock('@/components/common/SkeletonScreen.vue', () => ({
  default: { name: 'SkeletonScreen', template: '<div class="skeleton-stub" />' },
}))

// 两张用户侧卡片有权限门（hasPermission + auth.role）
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ role: 'user' }),
}))
vi.mock('@/config/permissions', () => ({
  hasPermission: () => true,
}))

// API mock：stats 方法与列表方法同模块，列表零调用即「不拉全量」的实锤
const { userApiMock, counselorApiMock, adminApiMock, alertsApiMock } = vi.hoisted(() => ({
  userApiMock: {
    getUserWarningStats: vi.fn(),
    getUserAssessmentHistoryStats: vi.fn(),
    getInterventionStats: vi.fn(),
    // 旧实现拉全量的列表方法（必须零调用）
    getUserWarnings: vi.fn(),
    getUserAssessmentHistory: vi.fn(),
    getDataHistory: vi.fn(),
    getInterventionHistory: vi.fn(),
  },
  counselorApiMock: {
    getCounselorWarningStats: vi.fn(),
    getCounselorUserStats: vi.fn(),
    getCounselorWarnings: vi.fn(),
    getCounselorUsers: vi.fn(),
  },
  adminApiMock: {
    getCrisisEventStats: vi.fn(),
    getOperationLogStats: vi.fn(),
    getCrisisEvents: vi.fn(),
    getOperationLogs: vi.fn(),
  },
  alertsApiMock: {
    getAlertHistoryStats: vi.fn(),
    getSilenceStats: vi.fn(),
    listAlertHistory: vi.fn(),
    listSilences: vi.fn(),
  },
}))

vi.mock('@/api/userApi', () => ({ userApi: userApiMock }))
vi.mock('@/api/counselorApi', () => ({ counselorApi: counselorApiMock }))
vi.mock('@/api/adminApi', () => ({ adminApi: adminApiMock }))
vi.mock('@/api/alertsApi', () => ({ alertsApi: alertsApiMock }))

interface CardCase {
  name: string
  component: unknown
  api: Record<string, ReturnType<typeof vi.fn>>
  statsMethod: string
  listMethods: string[]
  payload: Record<string, number>
  /** 渲染后 .stat-value 中必须出现的字符串（注意 avgCompletion 带 % 后缀） */
  expectTexts: string[]
}

const CASES: CardCase[] = [
  {
    name: 'WarningStatsCard（用户预警）',
    component: WarningStatsCard,
    api: userApiMock,
    statsMethod: 'getUserWarningStats',
    listMethods: ['getUserWarnings'],
    payload: { total: 187, high_risk: 61, medium_risk: 32, low_risk: 94, handled: 55, unread: 76 },
    expectTexts: ['187', '61', '32', '94', '55', '76'],
  },
  {
    name: 'AssessmentsStatsCard（评估历史）',
    component: AssessmentsStatsCard,
    api: userApiMock,
    statsMethod: 'getUserAssessmentHistoryStats',
    listMethods: ['getUserAssessmentHistory', 'getDataHistory'],
    payload: {
      total: 213,
      structured: 160,
      text: 43,
      physiological: 10,
      high_risk: 61,
      medium_risk: 32,
      low_risk: 94,
    },
    expectTexts: ['213', '160', '43', '10', '61', '32', '94'],
  },
  {
    name: 'InterventionStatsCard（干预计划）',
    component: InterventionStatsCard,
    api: userApiMock,
    statsMethod: 'getInterventionStats',
    listMethods: ['getInterventionHistory'],
    payload: { active: 100, completed: 60, cancelled: 4, avg_completion: 62 },
    expectTexts: ['100', '60', '4', '62%'],
  },
  {
    name: 'CounselorWarningStatsCard（咨询师预警）',
    component: CounselorWarningStatsCard,
    api: counselorApiMock,
    statsMethod: 'getCounselorWarningStats',
    listMethods: ['getCounselorWarnings'],
    payload: { total: 271, unhandled: 61, handled: 210, high_risk: 90, medium_risk: 32, low_risk: 88 },
    expectTexts: ['271', '61', '210', '90', '32', '88'],
  },
  {
    name: 'UserOverviewStatsCard（绑定用户分布）',
    component: UserOverviewStatsCard,
    api: counselorApiMock,
    statsMethod: 'getCounselorUserStats',
    listMethods: ['getCounselorUsers'],
    payload: { total: 165, none: 101, low: 12, medium: 23, high: 34, critical: 45 },
    expectTexts: ['165', '101', '12', '23', '34', '45'],
  },
  {
    name: 'CrisisEventStatsCard（危机事件）',
    component: CrisisEventStatsCard,
    api: adminApiMock,
    statsMethod: 'getCrisisEventStats',
    listMethods: ['getCrisisEvents'],
    payload: { total: 190, detected: 100, reviewed: 11, escalated: 60, resolved: 19 },
    expectTexts: ['190', '100', '11', '60', '19'],
  },
  {
    name: 'AlertStatsCard（告警历史）',
    component: AlertStatsCard,
    api: alertsApiMock,
    statsMethod: 'getAlertHistoryStats',
    listMethods: ['listAlertHistory'],
    payload: { total: 260, p0: 61, p1: 103, p2: 52, firing: 160, resolved: 157 },
    expectTexts: ['260', '61', '103', '52', '160', '157'],
  },
  {
    name: 'SilenceStatsCard（静默规则）',
    component: SilenceStatsCard,
    api: alertsApiMock,
    statsMethod: 'getSilenceStats',
    listMethods: ['listSilences'],
    payload: { total: 260, active: 200, inactive: 60 },
    expectTexts: ['260', '200', '60'],
  },
  {
    name: 'OperationLogStatsCard（操作日志）',
    component: OperationLogStatsCard,
    api: adminApiMock,
    statsMethod: 'getOperationLogStats',
    listMethods: ['getOperationLogs'],
    payload: { total: 214, user: 61, counselor: 52, admin: 43, super_admin: 58 },
    expectTexts: ['214', '61', '52', '43', '58'],
  },
]

describe('P1-15 统计卡聚合端点闸门（F-03 第六轮）', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  for (const c of CASES) {
    it(`${c.name}：只调聚合端点且渲染聚合值`, async () => {
      c.api[c.statsMethod].mockResolvedValue(c.payload)
      const wrapper = mount(c.component as never)
      await flushPromises()

      // 判据 1：聚合端点被调一次且无参（无 page_size 全量拉取）
      expect(c.api[c.statsMethod]).toHaveBeenCalledTimes(1)
      expect(c.api[c.statsMethod]).toHaveBeenCalledWith()
      // 判据 1（续）：任何列表方法零调用
      for (const listMethod of c.listMethods) {
        expect(c.api[listMethod]).not.toHaveBeenCalled()
      }

      // 判据 2：聚合字段渲染进瓦片，且没有瓦片停留在初始默认值 0
      const values = wrapper.findAll('.stat-value').map((el) => el.text())
      expect(values).toHaveLength(c.expectTexts.length)
      for (const text of c.expectTexts) {
        expect(values.some((v) => v.includes(text))).toBe(true)
      }
      expect(values.filter((v) => v === '0' || v === '0%')).toHaveLength(0)
      wrapper.unmount()
    })
  }

  it('聚合端点抛错时卡片静默降级为 0 且不阻断（既有降级语义不回退）', async () => {
    userApiMock.getUserWarningStats.mockRejectedValue(new Error('network'))
    const wrapper = mount(WarningStatsCard)
    await flushPromises()

    const values = wrapper.findAll('.stat-value').map((el) => el.text())
    expect(values).toHaveLength(6)
    expect(values.every((v) => v === '0')).toBe(true)
    // 降级后仍走完加载态（loading=false，骨架屏让位给瓦片）
    expect(wrapper.find('.skeleton-stub').exists()).toBe(false)
    wrapper.unmount()
  })
})

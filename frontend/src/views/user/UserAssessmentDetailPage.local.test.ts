/**
 * UserAssessmentDetailPage 本地渲染回归测试（FIX-2026-10-08）。
 *
 * 缺陷: 列表行 id 来自 `structured_assessments` / `text_entries` /
 *       `physiological_records`（后端 user_data_service.py:371-464），而详情端点
 *       `GET /user/risk/assessments/{id}` 查的是 `risk_assessments`
 *       （backend/app/api/v1/user_risk.py:112-139）—— **两个独立 ID 空间**。
 *       从列表点「查看详情」会拿列表的 id 去查另一张表，命中不了就是 404；
 *       万一撞上同号记录，显示的还是**别人/别的类型**的数据（临床场景最危险的一类错配）。
 *
 * 定夺: 前端本地渲染列表已下发的 `data` 载荷，不改后端。列表响应里已经带齐了
 *       详情所需的全部字段（structured 的 scale/severity/data_payload、text 的
 *       content 全文、physiological 的各项指标），再请求一次纯属多余。
 *
 * 为什么既有测试没抓到: `src/api/userRiskApi.test.ts` 只测了 API 函数本身
 *       （传 7 就断言请求 `/user/risk/assessments/7`），**没有任何挂载级测试**
 *       验证「详情页面真的拿到了对的数据」。
 *
 * 断言方式: 把后端真实响应形状放进 history.state（模拟从列表跳转），挂载真实组件，
 *       断言载荷里的字段真的渲染出来；并断言**没有**去请求那个会 404 的端点。
 *       `detailMock` 一律 reject 404 —— 这正是当前后端面对列表 id 的真实行为，
 *       改前这些用例会因「详情加载失败」而全红。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/i18n'

const { detailMock, routeState } = vi.hoisted(() => ({
  detailMock: vi.fn(),
  routeState: { id: '11' },
}))

vi.mock('@/api/userRiskApi', () => ({
  userRiskApi: { getAssessmentDetail: detailMock },
}))

const pushMock = vi.fn()
const backMock = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: routeState.id }, query: {} }),
  useRouter: () => ({ push: pushMock, back: backMock }),
}))

/** 后端 `GET /user/data/history` 的真实单项形状。 */
const STRUCTURED_ITEM = {
  id: 11,
  type: 'structured',
  created_at: '2026-10-01T08:30:00',
  data: { assessment_type: 'PHQ-9', score: 72.5, severity: 'high', data_payload: { q1: 3 } },
}

const TEXT_ITEM = {
  id: 12,
  type: 'text',
  created_at: '2026-10-02T09:00:00',
  data: {
    entry_type: 'diary',
    // 超过列表摘要的 60 字截断长度 —— 「查看详情」的全部价值就在这段被截断的全文
    content:
      '最近两周睡眠很差，几乎每天凌晨两三点才睡着，白天上课完全集中不了注意力，' +
      '和室友的交流也变少了，感觉自己什么都做不好，有时候会忍不住哭。',
    mood_score: 3,
    sentiment_score: 0.21,
    sentiment_label: 'negative',
  },
}

const PHYSIO_ITEM = {
  id: 13,
  type: 'physiological',
  created_at: '2026-10-03T07:00:00',
  data: {
    source: 'wearable',
    sleep_hours: 5.5,
    sleep_quality: 62,
    exercise_minutes: 20,
    heart_rate: 78,
    steps: 4200,
  },
}

async function mountDetail() {
  const wrapper = mount(await import('./UserAssessmentDetailPage.vue').then(m => m.default), {
    global: { plugins: [i18n] },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

function goToDetailWith(item: unknown) {
  const id = Number((item as { id?: number })?.id ?? 11)
  // 真实路由下 params.id 就是被点开的那条记录的 id
  routeState.id = String(id)
  window.history.replaceState(
    item ? { assessmentItem: JSON.stringify(item) } : {},
    '',
    `/user/assessments/${id}`
  )
}

/** 只改路由 id，不带载荷 —— 用于「载荷 id 与路由 id 不一致」的串号用例。 */
function goToDetailWithoutState(id: number) {
  routeState.id = String(id)
  window.history.replaceState({}, '', `/user/assessments/${id}`)
}

describe('UserAssessmentDetailPage 本地渲染（不改后端）', () => {
  beforeEach(() => {
    detailMock.mockReset()
    pushMock.mockReset()
    backMock.mockReset()
    // 真实后端行为：列表 id 在 risk_assessments 里查不到 → 404
    detailMock.mockRejectedValue(new Error('评估记录不存在'))
    routeState.id = '11'
    window.sessionStorage.clear()
    window.history.replaceState({}, '', '/user/assessments/11')
  })

  it('structured：渲染 data 载荷的量表/得分/严重度（改前请求后端 → 404 错误态）', async () => {
    goToDetailWith(STRUCTURED_ITEM)
    const wrapper = await mountDetail()

    const text = wrapper.text()
    expect(text).toContain('PHQ-9')
    expect(text).toContain('72.5')
    expect(text).toContain('较高')
    // 关键：不该再去打那个 ID 空间错配的端点
    expect(detailMock).not.toHaveBeenCalled()
  })

  it('text：渲染 content 全文（列表里被截断到 60 字的部分）', async () => {
    goToDetailWith(TEXT_ITEM)
    const wrapper = await mountDetail()

    expect(wrapper.text()).toContain('有时候会忍不住哭')
    expect(detailMock).not.toHaveBeenCalled()
  })

  it('physiological：渲染各项生理指标', async () => {
    goToDetailWith(PHYSIO_ITEM)
    const wrapper = await mountDetail()

    const text = wrapper.text()
    expect(text).toContain('wearable')
    expect(text).toContain('5.5')
    expect(text).toContain('4200')
    expect(detailMock).not.toHaveBeenCalled()
  })

  it('无本地载荷（直接访问 URL / 分享链接）：fail-closed 提示，不去请求会串号的端点', async () => {
    goToDetailWith(null)
    const wrapper = await mountDetail()

    // 必须给出可理解的说明，而不是「加载失败」或空白
    expect(wrapper.text()).toContain('从评估列表')
    expect(detailMock).not.toHaveBeenCalled()
  })

  it('载荷 id 与路由 id 不一致时不渲染（防止串号显示别人的记录）', async () => {
    routeState.id = '11'
    window.history.replaceState(
      { assessmentItem: JSON.stringify({ ...STRUCTURED_ITEM, id: 999 }) },
      '',
      '/user/assessments/11'
    )
    const wrapper = await mountDetail()

    expect(wrapper.text()).toContain('从评估列表')
    expect(wrapper.text()).not.toContain('PHQ-9')
  })

  it('损坏的载荷（data 不是对象）不抛异常', async () => {
    goToDetailWith({ id: 11, type: 'structured', created_at: null, data: 'not-an-object' })
    const wrapper = await mountDetail()

    expect(wrapper.text()).toBeTruthy()
    expect(detailMock).not.toHaveBeenCalled()
  })

  it('新标签页打开（无 history.state）时从 sessionStorage 快照取载荷', async () => {
    const { writeAssessmentDetailCache, CACHE_KEY } = await import('./utils/assessmentDetailCache')
    writeAssessmentDetailCache([STRUCTURED_ITEM, TEXT_ITEM])
    goToDetailWithoutState(11)

    const wrapper = await mountDetail()
    expect(wrapper.text()).toContain('PHQ-9')
    expect(wrapper.text()).toContain('72.5')
    expect(detailMock).not.toHaveBeenCalled()
    expect(window.sessionStorage.getItem(CACHE_KEY)).not.toBeNull()
  })

  it('快照里没有该 id 时同样 fail-closed（不拿邻近记录顶替）', async () => {
    const { writeAssessmentDetailCache } = await import('./utils/assessmentDetailCache')
    writeAssessmentDetailCache([TEXT_ITEM])
    goToDetailWithoutState(11)

    const wrapper = await mountDetail()
    expect(wrapper.text()).toContain('从评估列表')
  })
})

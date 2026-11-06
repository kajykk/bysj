/**
 * ROUND_34 / S-02：统计接口失败时不得把「加载失败」渲染成 0。
 *
 * 缺陷背景：M27（ROUND_23）已在模板写好三态（v-if 加载中 /
 * v-else-if="unhandledCount === null" 加载失败 / v-else 正常），
 * 但 loadStats 的 catch 只写 `// keep defaults`，unhandledCount 保持初值 0，
 * 失败态分支永远不可达 ⇒ 咨询师看到「0 条待处理预警」，是临床漏报信号。
 *
 * 替换层说明：这里替换的是**外部依赖**（counselorApi / i18n / router /
 * auth store / 子组件），因为它们需要网络与布局上下文；被测层是
 * CounselorDashboard 组件自身的 catch 状态转移与真实模板渲染输出（DOM）。
 * 缺陷不在被替换层，故挂载级断言能真实区分修复前后：把
 * `unhandledCount.value = null` 删掉，下面的失败用例立即红。
 *
 * 本文件与既有 CounselorDashboard.test.ts 的「源码结构见证」互补：
 * 那里证明分支存在，这里证明分支在运行时真的会被走到。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const mocks = vi.hoisted(() => ({
  unhandled: vi.fn(),
  users: vi.fn(),
  bindCode: vi.fn(),
}))

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (key: string) => key }) }
})
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ role: 'counselor', logout: vi.fn() }),
}))
vi.mock('@/api/counselorApi', () => ({
  counselorApi: {
    getCounselorUnhandledWarningCount: mocks.unhandled,
    getCounselorUserCount: mocks.users,
    getCounselorBindCode: mocks.bindCode,
    refreshCounselorBindCode: vi.fn(),
  },
}))

import CounselorDashboard from './CounselorDashboard.vue'

const CountUpStub = defineComponent({
  name: 'CountUpStub',
  props: { end: { type: Number, default: 0 }, duration: { type: Number, default: 0 } },
  setup: (props) => () => h('span', { class: 'count-up-stub' }, String(props.end)),
})

const BentoStub = defineComponent({
  name: 'BentoStub',
  props: { title: { type: String, default: '' } },
  setup: (_props, { slots }) => () =>
    h('div', { class: 'bento-stub' }, [
      slots.actions?.(),
      slots.default?.(),
      slots.footer?.(),
    ]),
})

const slotStub = (tag: string) =>
  defineComponent({
    setup: (_props, { slots }) => () => h(tag, {}, slots.default?.()),
  })

const stubs = {
  CountUp: CountUpStub,
  BentoCell: BentoStub,
  AppIcon: slotStub('i'),
  SkeletonScreen: slotStub('div'),
  'el-tag': slotStub('span'),
  'el-button': slotStub('button'),
  'el-icon': slotStub('i'),
}

const mountDashboard = () =>
  mount(CounselorDashboard, {
    global: { stubs },
  })

describe('CounselorDashboard - S-02 统计失败三态（挂载级）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.bindCode.mockRejectedValue(new Error('bind code unavailable'))
  })

  it('统计接口 reject 时进入失败态：显示破折号 + 失败文案，hero 区不出现 0', async () => {
    mocks.unhandled.mockRejectedValue(new Error('timeout'))
    mocks.users.mockRejectedValue(new Error('timeout'))

    const wrapper = mountDashboard()
    await flushPromises()

    // 加载中态已结束，失败态分支必须真正被渲染出来
    expect(wrapper.find('.skeleton').exists()).toBe(false)
    expect(wrapper.find('.stat-sub--muted').exists()).toBe(true)
    expect(wrapper.find('.stat-sub--muted').text()).toContain('counselorDashboard.heroLoadFailed')

    const heroStat = wrapper.find('.stat--warning')
    expect(heroStat.exists()).toBe(true)
    expect(heroStat.text()).toContain('—')
    expect(heroStat.text()).not.toContain('0')
    // 正常分支的数字动画不得出现（它渲染的会是初值 0）
    expect(heroStat.find('.count-up-stub').exists()).toBe(false)
    wrapper.unmount()
  })

  it('统计接口成功时仍渲染真实数字（混合输入，防止「永远失败态」蒙混）', async () => {
    mocks.unhandled.mockResolvedValue(7)
    mocks.users.mockResolvedValue(3)

    const wrapper = mountDashboard()
    await flushPromises()

    expect(wrapper.find('.stat-sub--muted').exists()).toBe(false)
    const heroStat = wrapper.find('.stat--warning')
    expect(heroStat.find('.count-up-stub').exists()).toBe(true)
    expect(heroStat.find('.count-up-stub').text()).toBe('7')
    wrapper.unmount()
  })
})

/**
 * OnboardingTour 受控绑定回归测试。
 *
 * 缺陷背景（本文件钉住的正是它）：
 * 模板曾写成 `<el-tour :current="currentStep">` —— 单向绑定。Element Plus 2.14
 * 的 el-tour 是通过 `update:current` 事件上报步骤变化的（见
 * node_modules/element-plus/es/components/tour/src/tour2.mjs 的 next/prev 实现），
 * 父层没监听该事件，`currentStep` 永远停在 0，用户点「下一步」时视图不前进。
 *
 * 替换层说明：这里用最小 stub 复刻 el-tour 的受控契约（`current` prop 入、
 * `update:current` 出），因为真实 el-tour 依赖 target 元素定位，jsdom 里没有
 * 布局上下文。缺陷位于**父层绑定**（被测层），而 stub 提供的子层契约在
 * Element Plus 源码里已核实，故本用例能真实区分修复前后。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return {
    ...actual,
    useI18n: () => ({ t: (key: string) => key }),
  }
})

import OnboardingTour from './OnboardingTour.vue'
import { resetOnboardingState } from '@/composables/useOnboarding'

/** 复刻 Element Plus el-tour 的受控契约：current 入、update:current 出 */
const ElTourStub = defineComponent({
  name: 'ElTour',
  props: {
    modelValue: { type: Boolean, default: false },
    current: { type: Number, default: 0 },
  },
  emits: ['update:modelValue', 'update:current', 'finish', 'close'],
  setup(props, { emit, slots }) {
    const steps = () => slots.default?.()
    return () =>
      props.modelValue
        ? h('div', { class: 'el-tour-stub', 'data-current': String(props.current) }, [
            h('div', { class: 'stub-steps' }, steps()),
            h(
              'button',
              {
                class: 'stub-next',
                onClick: () => emit('update:current', props.current + 1),
              },
              'next'
            ),
            h(
              'button',
              {
                class: 'stub-finish',
                onClick: () => emit('finish'),
              },
              'finish'
            ),
          ])
        : null
  },
})

const ElTourStepStub = defineComponent({
  name: 'ElTourStep',
  props: {
    target: { type: String, default: '' },
    title: { type: String, default: '' },
    description: { type: String, default: '' },
    placement: { type: String, default: '' },
  },
  setup: () => () => h('div', { class: 'el-tour-step-stub' }),
})

const mountTour = (role = 'admin') =>
  mount(OnboardingTour, {
    props: { role },
    global: {
      stubs: { ElTour: ElTourStub, ElTourStep: ElTourStepStub },
    },
  })

describe('OnboardingTour 步骤绑定', () => {
  beforeEach(() => {
    localStorage.clear()
    resetOnboardingState()
  })

  it('收到 update:current 后 currentStep 跟随（修复前：停在 0，此断言失败）', async () => {
    const wrapper = mountTour('admin')
    await wrapper.vm.tryStartOnboarding()
    await wrapper.vm.$nextTick()

    const tour = wrapper.findComponent(ElTourStub)
    expect(tour.exists()).toBe(true)
    expect(tour.props('current')).toBe(0)

    await wrapper.find('.stub-next').trigger('click')
    await wrapper.vm.$nextTick()

    // 单向绑定 `:current` 时这里仍是 0 —— 正是用户遇到的「点 Next 没反应」
    expect(tour.props('current')).toBe(1)

    // 连续前进也要逐次跟随（避免「只跳一次」的假修复）
    await wrapper.find('.stub-next').trigger('click')
    await wrapper.vm.$nextTick()
    expect(tour.props('current')).toBe(2)
  })

  it('推进步骤后完成引导会写入按角色隔离的完成标记', async () => {
    const wrapper = mountTour('admin')
    await wrapper.vm.tryStartOnboarding()
    await wrapper.find('.stub-next').trigger('click')
    await wrapper.vm.$nextTick()
    await wrapper.find('.stub-finish').trigger('click')
    await wrapper.vm.$nextTick()

    expect(localStorage.getItem('dws:onboarding:completed:admin:v1')).toBe('true')
    // 关闭状态通过 v-model 回传，stub 应当不再渲染
    expect(wrapper.findComponent(ElTourStub).props('modelValue')).toBe(false)
  })

  it('未开始引导时不渲染 tour（isOpen 受控为 false）', () => {
    const wrapper = mountTour('admin')
    // 断言 DOM 而非组件实例：stub 在 modelValue=false 时渲染 null，
    // findComponent 仍会命中实例，无法区分「未打开」。
    expect(wrapper.find('.el-tour-stub').exists()).toBe(false)
    expect(wrapper.findComponent(ElTourStub).props('modelValue')).toBe(false)
  })

  it('restartTour 会把步骤复位到 0 并重新打开', async () => {
    const wrapper = mountTour('admin')
    await wrapper.vm.tryStartOnboarding()
    await wrapper.find('.stub-next').trigger('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.findComponent(ElTourStub).props('current')).toBe(1)

    await wrapper.vm.restartTour()
    await wrapper.vm.$nextTick()
    expect(wrapper.findComponent(ElTourStub).props('current')).toBe(0)
    expect(wrapper.findComponent(ElTourStub).props('modelValue')).toBe(true)
  })
})

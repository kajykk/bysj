/* UI-B4 回归测试：BaseChart 迁到 vue-echarts 后保留的对外契约 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import BaseChart from './BaseChart.vue'

const { chartMock, mockResize, mockDispatchAction, mockGetDataURL, mockSetOption } = vi.hoisted(() => {
  const chartMock = {
    dispatchAction: vi.fn(),
    getDataURL: vi.fn(() => 'data:image/png;base64,stub'),
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  }
  return {
    chartMock,
    mockResize: chartMock.resize,
    mockDispatchAction: chartMock.dispatchAction,
    mockGetDataURL: chartMock.getDataURL,
    mockSetOption: chartMock.setOption,
  }
})

vi.mock('vue-echarts', async () => {
  const { defineComponent, h, onMounted } = await import('vue')
  return {
    default: defineComponent({
      name: 'VChartStub',
      props: {
        option: { type: Object, default: () => ({}) },
        theme: { type: [String, Object], default: undefined },
        autoresize: { type: [Boolean, Object], default: false },
        updateOptions: { type: Object, default: undefined },
      },
      emits: ['finished'],
      setup(_props, { emit, expose }) {
        onMounted(() => emit('finished'))
        expose({
          chart: chartMock,
          resize: mockResize,
          dispatchAction: mockDispatchAction,
          getDataURL: mockGetDataURL,
        })
        return () => h('div', { class: 'vchart-stub' })
      },
    }),
  }
})

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

beforeEach(() => {
  vi.clearAllMocks()
})

const baseProps = {
  option: { title: { text: 'test' } },
  autoResize: true,
}

const vchart = (wrapper: ReturnType<typeof mount>) =>
  wrapper.findComponent({ name: 'VChartStub' })

describe('BaseChart - UI-B4 vue-echarts 契约', () => {
  it('1. 挂载后渲染 VChart，并传递 option / autoresize / 全量替换选项', async () => {
    const wrapper = mount(BaseChart, { props: baseProps })
    await flushPromises()

    const chart = vchart(wrapper)
    expect(chart.exists()).toBe(true)
    expect(chart.props('option')).toEqual(baseProps.option)
    expect(chart.props('autoresize')).toBe(true)
    expect(chart.props('updateOptions')).toEqual({ notMerge: true })
    expect(wrapper.emitted('chartReady')?.[0]?.[0]).toBe(chartMock)

    wrapper.unmount()
  })

  it('2. 未显式指定 theme 时注入令牌主题；显式传入时原样透传', async () => {
    const themed = mount(BaseChart, { props: baseProps })
    await flushPromises()
    const theme = vchart(themed).props('theme') as Record<string, unknown>
    expect(theme).toMatchObject({ backgroundColor: 'transparent' })
    expect(Array.isArray(theme.color)).toBe(true)
    expect(theme.categoryAxis).toBeDefined()
    themed.unmount()

    const explicit = mount(BaseChart, { props: { ...baseProps, theme: 'dark' } })
    await flushPromises()
    expect(vchart(explicit).props('theme')).toBe('dark')
    explicit.unmount()
  })

  it('3. autoResize=false 时不开启自动尺寸同步', async () => {
    const wrapper = mount(BaseChart, { props: { ...baseProps, autoResize: false } })
    await flushPromises()

    expect(vchart(wrapper).props('autoresize')).toBe(false)

    wrapper.unmount()
  })

  it('4. 键盘 Enter/Space 触发首系列高亮，Space 阻止滚动', async () => {
    const wrapper = mount(BaseChart, { props: baseProps })
    await flushPromises()

    await wrapper.trigger('keydown.enter')
    expect(mockDispatchAction).toHaveBeenCalledWith({ type: 'highlight', seriesIndex: 0, dataIndex: 0 })

    const event = new KeyboardEvent('keydown', { key: ' ', cancelable: true })
    await wrapper.element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(mockDispatchAction).toHaveBeenCalledTimes(2)

    wrapper.unmount()
  })

  it('5. 暴露 getInstance / resize / setOption / exportImage', async () => {
    const wrapper = mount(BaseChart, { props: baseProps })
    await flushPromises()

    const vm = wrapper.vm as unknown as {
      getInstance: () => unknown
      resize: () => void
      setOption: (option: Record<string, unknown>) => void
      exportImage: (type?: 'png' | 'svg' | 'jpeg', pixelRatio?: number) => string | undefined
    }

    expect(vm.getInstance()).toBe(chartMock)
    vm.resize()
    expect(mockResize).toHaveBeenCalled()
    vm.setOption({ title: { text: 'next' } })
    expect(mockSetOption).toHaveBeenCalledWith({ title: { text: 'next' } }, true)
    expect(vm.exportImage('svg', 3)).toBe('data:image/png;base64,stub')
    expect(mockGetDataURL).toHaveBeenCalledWith({ type: 'svg', pixelRatio: 3 })

    wrapper.unmount()
  })

  it('6. keep-alive 停用卸载图表，重新激活后重新挂载', async () => {
    const Dummy = { name: 'Dummy', template: '<div />' }
    const Parent = {
      components: { BaseChart, Dummy },
      data() {
        return { current: 'BaseChart', option: { title: { text: 'test' } } }
      },
      template: `
        <keep-alive>
          <component :is="current" :option="option" :autoResize="true" />
        </keep-alive>
      `,
    }
    const wrapper = mount(Parent)
    await flushPromises()

    expect(wrapper.findComponent({ name: 'VChartStub' }).exists()).toBe(true)

    await wrapper.setData({ current: 'Dummy' })
    await flushPromises()
    expect(wrapper.findComponent({ name: 'VChartStub' }).exists()).toBe(false)

    await wrapper.setData({ current: 'BaseChart' })
    await flushPromises()
    expect(wrapper.findComponent({ name: 'VChartStub' }).exists()).toBe(true)
  })

  it('7. 保留 role=img / aria-label / aria-describedby 无障碍契约', async () => {
    const wrapper = mount(BaseChart, {
      props: { ...baseProps, description: '近 30 天风险走势' },
    })
    await flushPromises()

    const root = wrapper.element as HTMLElement
    expect(root.getAttribute('role')).toBe('img')
    expect(root.getAttribute('aria-label')).toBe('charts.baseAriaLabel')
    const describedBy = root.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    expect(wrapper.find(`#${describedBy}`).text()).toBe('近 30 天风险走势')

    wrapper.unmount()
  })
})

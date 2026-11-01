import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, withDirectives } from 'vue'
import { mount } from '@vue/test-utils'
import { vAutoAnimate } from './autoAnimate'

const mocks = vi.hoisted(() => {
  const enable = vi.fn()
  const disable = vi.fn()
  const isEnabled = vi.fn(() => true)
  const autoAnimate = vi.fn(() => ({
    parent: {} as Element,
    enable,
    disable,
    isEnabled,
  }))
  return { autoAnimate, enable, disable, isEnabled }
})

vi.mock('@formkit/auto-animate', () => ({ default: mocks.autoAnimate }))

type MediaListener = (event: MediaQueryListEvent) => void

let mediaMatches = false
let mediaListeners = new Set<MediaListener>()

const addEventListener = vi.fn((_: string, listener: MediaListener) => {
  mediaListeners.add(listener)
})
const removeEventListener = vi.fn((_: string, listener: MediaListener) => {
  mediaListeners.delete(listener)
})
const matchMedia = vi.fn(
  () =>
    ({
      get matches() {
        return mediaMatches
      },
      media: '(prefers-reduced-motion: reduce)',
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener,
      removeEventListener,
      dispatchEvent: vi.fn(),
    }) as unknown as MediaQueryList,
)

function emitMotion(matches: boolean) {
  mediaMatches = matches
  for (const listener of mediaListeners) listener({ matches } as MediaQueryListEvent)
}

const Host = defineComponent({
  props: { disabled: { type: Boolean, default: false } },
  setup(props) {
    return () =>
      withDirectives(h('ul', [h('li', { key: 1 }, 'one'), h('li', { key: 2 }, 'two')]), [
        [vAutoAnimate, { duration: 180, easing: 'ease-out', disabled: props.disabled }],
      ])
  },
})

beforeEach(() => {
  vi.clearAllMocks()
  mediaMatches = false
  mediaListeners = new Set()
  vi.stubGlobal('matchMedia', matchMedia)
  Object.defineProperty(HTMLElement.prototype, 'animate', {
    configurable: true,
    writable: true,
    value: vi.fn(),
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  delete (HTMLElement.prototype as { animate?: unknown }).animate
})

describe('v-auto-animate', () => {
  it('挂载时把过滤后的时长/缓动传给 auto-animate，并默认启用', () => {
    mount(Host)

    expect(mocks.autoAnimate).toHaveBeenCalledTimes(1)
    expect(mocks.autoAnimate.mock.calls[0][1]).toEqual({
      disrespectUserMotionPreference: false,
      duration: 180,
      easing: 'ease-out',
    })
    expect(mocks.enable).toHaveBeenCalledTimes(1)
    expect(mocks.disable).not.toHaveBeenCalled()
  })

  it('disabled 运行时切换只启停控制器，不重建 observer', async () => {
    const wrapper = mount(Host)

    await wrapper.setProps({ disabled: true })
    expect(mocks.disable).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ disabled: false })
    expect(mocks.enable).toHaveBeenCalledTimes(2)
    expect(mocks.autoAnimate).toHaveBeenCalledTimes(1)
  })

  it('reduced-motion 时挂载即禁用，并跟随系统偏好变化启停', () => {
    mediaMatches = true
    mount(Host)

    expect(addEventListener).toHaveBeenCalledWith('change', expect.any(Function))
    expect(mocks.disable).toHaveBeenCalledTimes(1)

    emitMotion(false)
    expect(mocks.enable).toHaveBeenCalledTimes(1)

    emitMotion(true)
    expect(mocks.disable).toHaveBeenCalledTimes(2)
  })

  it('绑定值 false 等价于 disabled', () => {
    const BooleanHost = defineComponent({
      setup: () => () => withDirectives(h('ul', [h('li', 'one')]), [[vAutoAnimate, false]]),
    })
    mount(BooleanHost)

    expect(mocks.disable).toHaveBeenCalledTimes(1)
    expect(mocks.enable).not.toHaveBeenCalled()
  })

  it('屏蔽 disrespectUserMotionPreference，避免调用方绕过减动效约定', () => {
    const OverrideHost = defineComponent({
      setup: () =>
        () =>
          withDirectives(h('ul', [h('li', 'one')]), [
            [vAutoAnimate, { duration: 120, disrespectUserMotionPreference: true }],
          ]),
    })
    mount(OverrideHost)

    expect(mocks.autoAnimate.mock.calls[0][1]).toEqual({
      disrespectUserMotionPreference: false,
      duration: 120,
    })
  })

  it('卸载时移除媒体查询监听并停用控制器', () => {
    const wrapper = mount(Host)
    wrapper.unmount()

    expect(removeEventListener).toHaveBeenCalledWith('change', expect.any(Function))
    expect(mocks.disable).toHaveBeenCalledTimes(1)
  })

  it('无 Web Animations API 时不创建控制器', () => {
    delete (HTMLElement.prototype as { animate?: unknown }).animate
    mount(Host)

    expect(mocks.autoAnimate).not.toHaveBeenCalled()
  })
})

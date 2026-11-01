import autoAnimate, {
  type AnimationController,
  type AutoAnimateOptions,
} from '@formkit/auto-animate'
import type { Directive, DirectiveBinding } from 'vue'

/**
 * 动效指令：只负责「同一父容器内子节点增删/移动」的连续过渡。
 * 弹层、页签等已有 Element Plus 自身过渡，不在此重复接管。
 */
export interface AutoAnimateDirectiveOptions {
  duration?: number
  easing?: AutoAnimateOptions['easing']
  disabled?: boolean
}

type AutoAnimateBinding = boolean | AutoAnimateDirectiveOptions | undefined

interface AutoAnimateState {
  controller: AnimationController
  media: MediaQueryList | null
  disabled: boolean
  onChange: (() => void) | null
}

const states = new WeakMap<HTMLElement, AutoAnimateState>()

function resolveOptions(value: AutoAnimateBinding): AutoAnimateDirectiveOptions {
  if (typeof value === 'boolean') return { disabled: !value }
  return typeof value === 'object' && value !== null ? value : {}
}

function animationConfig(options: AutoAnimateDirectiveOptions): Partial<AutoAnimateOptions> {
  const config: Partial<AutoAnimateOptions> = { disrespectUserMotionPreference: false }
  if (typeof options.duration === 'number') config.duration = options.duration
  if (typeof options.easing === 'string') config.easing = options.easing
  return config
}

function reducedMotionQuery(): MediaQueryList | null {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null
  return window.matchMedia('(prefers-reduced-motion: reduce)')
}

function applyMotionPreference(state: AutoAnimateState) {
  if (state.disabled || state.media?.matches) state.controller.disable()
  else state.controller.enable()
}

function mounted(el: HTMLElement, binding: DirectiveBinding<AutoAnimateBinding>) {
  // auto-animate 依赖 Web Animations API；jsdom 等无 WAAPI 环境直接不挂
  // MutationObserver，避免测试环境在列表更新时抛错。
  if (typeof el.animate !== 'function') return

  const options = resolveOptions(binding.value)
  const controller = autoAnimate(el, animationConfig(options))
  const state: AutoAnimateState = {
    controller,
    media: reducedMotionQuery(),
    disabled: options.disabled === true,
    onChange: null,
  }
  state.onChange = () => applyMotionPreference(state)
  applyMotionPreference(state)
  state.media?.addEventListener('change', state.onChange)
  states.set(el, state)
}

function updated(el: HTMLElement, binding: DirectiveBinding<AutoAnimateBinding>) {
  const state = states.get(el)
  if (!state) return
  // duration/easing 只在挂载时生效：auto-animate 没有更新配置的 API，
  // 重建会叠加 MutationObserver。这里只响应 disabled 的运行时切换。
  state.disabled = resolveOptions(binding.value).disabled === true
  applyMotionPreference(state)
}

function unmounted(el: HTMLElement) {
  const state = states.get(el)
  if (!state) return
  if (state.onChange) state.media?.removeEventListener('change', state.onChange)
  state.controller.disable()
  states.delete(el)
}

export const vAutoAnimate: Directive<HTMLElement, AutoAnimateBinding> = {
  mounted,
  updated,
  unmounted,
}

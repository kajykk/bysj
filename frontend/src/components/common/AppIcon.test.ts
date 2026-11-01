import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AppIcon from './AppIcon.vue'

describe('AppIcon', () => {
  it('按短名解析到 tabler 集合并渲染 svg', () => {
    const wrapper = mount(AppIcon, { props: { name: 'home' } })
    const svg = wrapper.find('svg')
    expect(svg.exists()).toBe(true)
    expect(svg.attributes('width')).toBe('1em')
    expect(wrapper.attributes('aria-hidden')).toBe('true')
  })

  it('支持完整图标名与自定义尺寸', () => {
    const wrapper = mount(AppIcon, { props: { name: 'tabler:bell', size: 20 } })
    expect(wrapper.find('svg').attributes('width')).toBe('20')
  })
})

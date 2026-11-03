/**
 * 文本概览历史行不能只显示 ML 的「低风险」：危机规则命中的记录
 * 若没有额外标记，用户回看历史时会把一次危机误读成正常结果。
 *
 * jsdom 下 Element Plus 的 el-table 依赖真实布局，不渲染行；这里用
 * 轻量 stub 把 data 通过 provide 传给 column stub，直接调用列的
 * 作用域插槽，从而覆盖真实模板中的行内容。
 */
import { describe, it, expect } from 'vitest'
import { defineComponent, h, inject, provide } from 'vue'
import { mount } from '@vue/test-utils'
import i18n from '@/i18n'
import TextPredictionHistoryCard from './TextPredictionHistoryCard.vue'
import type { TextPredictionHistoryItem } from './composables/useTextPredictionHistory'

const rowsKey = Symbol('rows')

const ElTableStub = defineComponent({
  props: { data: { type: Array, default: () => [] } },
  setup(props, { slots }) {
    provide(rowsKey, props.data)
    return () => h('div', { class: 'el-table-stub' }, slots.default?.())
  },
})

const ElTableColumnStub = defineComponent({
  setup(_, { slots }) {
    const rows = inject<Record<string, unknown>[]>(rowsKey, [])
    return () =>
      h(
        'div',
        { class: 'el-table-column-stub' },
        rows.map((row) => slots.default?.({ row })),
      )
  },
})

function makeHistoryItem(overrides: Partial<TextPredictionHistoryItem> = {}): TextPredictionHistoryItem {
  return {
    prediction: 0,
    probability: 0.2,
    sentiment_label: 'negative',
    sentiment_score: 0.29,
    model_used: 'text_improved_bilingual_model',
    time: '2026-11-01 23:35',
    content_preview: '最近不想再继续',
    source: 'model',
    label_source: 'ml',
    ...overrides,
  }
}

function mountCard(history: TextPredictionHistoryItem[]) {
  return mount(TextPredictionHistoryCard, {
    props: { history },
    global: {
      plugins: [i18n],
      stubs: { 'el-table': ElTableStub, 'el-table-column': ElTableColumnStub },
    },
  })
}

describe('TextPredictionHistoryCard 危机标记', () => {
  it('危机命中的历史行除预测结果外还显示危机标记', () => {
    const wrapper = mountCard([makeHistoryItem({ crisis_detected: true })])
    const result = wrapper.find('.history-result')
    expect(result.exists()).toBe(true)
    expect(result.text()).toContain('0（低风险）')
    expect(result.text()).toContain('危机')
  })

  it('普通历史行不显示危机标记', () => {
    const wrapper = mountCard([makeHistoryItem()])
    const result = wrapper.find('.history-result')
    expect(result.exists()).toBe(true)
    expect(result.text()).not.toContain('危机')
  })
})

describe('TextPredictionHistoryCard 判定来源', () => {
  it('模型流历史标注为模型原始判定', () => {
    const wrapper = mountCard([makeHistoryItem()])
    const result = wrapper.find('.history-result')
    expect(result.text()).toContain('模型原始')
    expect(result.text()).not.toContain('融合')
  })

  it('日记流历史标注为融合判定', () => {
    const wrapper = mountCard([
      makeHistoryItem({ source: 'text', label_source: 'fused' }),
    ])
    const result = wrapper.find('.history-result')
    expect(result.text()).toContain('融合')
    expect(result.text()).not.toContain('模型原始')
  })
})

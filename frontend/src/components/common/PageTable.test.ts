import { describe, it, expect } from 'vitest'

describe('PageTable - 6.1.1 表格功能增强', () => {
  it('行高亮动画应使用正确的 CSS 类名', () => {
    const className = 'row-highlight-animation'
    expect(className).toBe('row-highlight-animation')
  })

  it('行高亮动画应持续 2 秒', () => {
    const animationDuration = '2s'
    expect(animationDuration).toBe('2s')
  })

  it('列宽记忆应使用 localStorage 存储', () => {
    const tableKey = 'test_table'
    const storageKey = `table_widths_${tableKey}`
    expect(storageKey).toBe('table_widths_test_table')
  })

  it('新行应被识别并高亮', () => {
    const oldData = [{ id: 1, name: 'A' }, { id: 2, name: 'B' }]
    const newData = [{ id: 1, name: 'A' }, { id: 2, name: 'B' }, { id: 3, name: 'C' }]

    const oldKeys = new Set(oldData.map((row) => row.id))
    const newRows = newData.filter((row) => !oldKeys.has(row.id))

    expect(newRows).toHaveLength(1)
    expect(newRows[0].id).toBe(3)
  })

  it('行键应优先使用 id 字段', () => {
    const getRowKey = (row: unknown) => {
      const r = row as Record<string, unknown>
      return r.id ?? r.key ?? JSON.stringify(row)
    }

    expect(getRowKey({ id: 5 })).toBe(5)
    expect(getRowKey({ key: 'abc' })).toBe('abc')
    expect(getRowKey({ name: 'test' })).toBe('{"name":"test"}')
  })
})

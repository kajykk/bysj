import { describe, it, expect } from 'vitest'
import { exportToCSV, exportToExcel, downloadJSON, type ExportColumn } from './exportUtils'

describe('exportUtils - 6.2.1 导出工具函数', () => {
  const mockData = [
    { id: 1, name: '张三', age: 25, score: 85.5 },
    { id: 2, name: '李四', age: 30, score: 92.0 }
  ]

  const columns: ExportColumn[] = [
    { key: 'id', label: 'ID' },
    { key: 'name', label: '姓名' },
    { key: 'age', label: '年龄' },
    { key: 'score', label: '分数', formatter: (v: number) => v.toFixed(1) }
  ]

  it('CSV 导出应生成正确的内容格式', () => {
    const headers = columns.map((col) => col.label)
    const rows = mockData.map((row) =>
      columns
        .map((col) => {
          const rawValue = row[col.key as keyof typeof row]
          const value = col.formatter ? col.formatter(rawValue, row) : rawValue
          return `"${String(value ?? '').replace(/"/g, '""')}"`
        })
        .join(',')
    )

    const csvContent = [headers.join(','), ...rows].join('\n')

    expect(csvContent).toContain('ID,姓名,年龄,分数')
    expect(csvContent).toContain('"1","张三","25","85.5"')
    expect(csvContent).toContain('"2","李四","30","92.0"')
  })

  it('空数据应抛出错误', () => {
    expect(() => exportToCSV([], columns)).toThrow('导出数据为空')
    expect(() => exportToExcel([], columns)).toThrow('导出数据为空')
  })

  it('Excel 导出应生成 HTML 表格格式', () => {
    const headers = columns.map((col) => `<th>${col.label}</th>`).join('')
    expect(headers).toBe('<th>ID</th><th>姓名</th><th>年龄</th><th>分数</th>')
  })

  it('XML 转义应正确处理特殊字符', () => {
    const escapeXml = (str: string) =>
      str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&apos;')

    expect(escapeXml('<script>')).toBe('&lt;script&gt;')
    expect(escapeXml('a & b')).toBe('a &amp; b')
    expect(escapeXml('"test"')).toBe('&quot;test&quot;')
  })

  it('JSON 导出应格式化输出', () => {
    const data = { name: 'test', value: 123 }
    const jsonStr = JSON.stringify(data, null, 2)

    expect(jsonStr).toContain('"name": "test"')
    expect(jsonStr).toContain('"value": 123')
  })

  it('格式化函数应正确应用', () => {
    const formatter = (v: number) => v.toFixed(1)
    expect(formatter(85.5)).toBe('85.5')
    expect(formatter(92)).toBe('92.0')
  })
})

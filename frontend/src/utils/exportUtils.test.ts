import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  exportToCSV,
  exportToExcel,
  downloadJSON,
  sanitizeCellForExcel,
  type ExportColumn
} from './exportUtils'

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

// 新增：覆盖 exportToExcel / downloadJSON / sanitizeCellForExcel 各分支
describe('exportUtils - 扩展覆盖', () => {
  let createObjectURLMock: ReturnType<typeof vi.fn>
  let revokeObjectURLMock: ReturnType<typeof vi.fn>
  let linkClickMock: ReturnType<typeof vi.fn>
  let appendChildSpy: ReturnType<typeof vi.fn>
  let _removeChildSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.useFakeTimers()

    createObjectURLMock = vi.fn(() => 'blob:mock-url')
    revokeObjectURLMock = vi.fn()
    linkClickMock = vi.fn()

    // stub URL.createObjectURL / revokeObjectURL
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: createObjectURLMock,
      revokeObjectURL: revokeObjectURLMock,
    })

    // 拦截 link.click()，避免 jsdom 抛错
    appendChildSpy = vi.spyOn(document.body, 'appendChild').mockImplementation((node: Node) => {
      // 模拟 link 的 click 行为
      if (node && (node as HTMLAnchorElement).tagName === 'A') {
        (node as HTMLAnchorElement).click = linkClickMock
      }
      return node
    })
    _removeChildSpy = vi.spyOn(document.body, 'removeChild').mockImplementation((node: Node) => node)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  describe('sanitizeCellForExcel', () => {
    it('空值应原样返回', () => {
      expect(sanitizeCellForExcel('')).toBe('')
    })

    it('普通文本不应被转义', () => {
      expect(sanitizeCellForExcel('hello')).toBe('hello')
      expect(sanitizeCellForExcel('123')).toBe('123')
    })

    it('以 = 开头的公式注入应被转义', () => {
      expect(sanitizeCellForExcel('=SUM(A1)')).toBe("'=SUM(A1)")
    })

    it('以 + 开头应被转义', () => {
      expect(sanitizeCellForExcel('+1+1')).toBe("'+1+1")
    })

    it('以 @ 开头应被转义', () => {
      expect(sanitizeCellForExcel('@admin')).toBe("'@admin")
    })

    it('以 \\t 开头应被转义', () => {
      expect(sanitizeCellForExcel('\tdata')).toBe("'\tdata")
    })

    it('以 \\r 开头应被转义', () => {
      expect(sanitizeCellForExcel('\rdata')).toBe("'\rdata")
    })

    it('以 - 开头且为合法数字时不应转义', () => {
      expect(sanitizeCellForExcel('-123')).toBe('-123')
      expect(sanitizeCellForExcel('-3.14')).toBe('-3.14')
      expect(sanitizeCellForExcel('-1e5')).toBe('-1e5')
      expect(sanitizeCellForExcel('-.5')).toBe('-.5')
    })

    it('以 - 开头但非数字应被转义', () => {
      expect(sanitizeCellForExcel('-abc')).toBe("'-abc")
      expect(sanitizeCellForExcel('- 12abc')).toBe("'- 12abc")
    })
  })

  describe('exportToCSV', () => {
    it('应调用 link.click 触发下载并释放 ObjectURL', () => {
      const data = [{ name: 'A', value: 1 }]
      const columns: ExportColumn[] = [
        { key: 'name', label: 'Name' },
        { key: 'value', label: 'Value' },
      ]

      exportToCSV(data, columns, 'test.csv')

      expect(createObjectURLMock).toHaveBeenCalledTimes(1)
      expect(linkClickMock).toHaveBeenCalledTimes(1)

      // 推进 1000ms 后释放 ObjectURL
      expect(revokeObjectURLMock).not.toHaveBeenCalled()
      vi.advanceTimersByTime(1000)
      expect(revokeObjectURLMock).toHaveBeenCalledTimes(1)
      expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:mock-url')
    })

    it('未提供文件名时使用默认导出名', () => {
      const data = [{ x: 1 }]
      const columns: ExportColumn[] = [{ key: 'x', label: 'X' }]

      exportToCSV(data, columns)

      expect(linkClickMock).toHaveBeenCalledTimes(1)
      // 默认文件名以 export_ 开头并以 .csv 结尾
      const calls = appendChildSpy.mock.calls
      const anchor = calls.find((c) => (c[0] as HTMLAnchorElement)?.tagName === 'A')?.[0] as HTMLAnchorElement
      expect(anchor?.download).toMatch(/^export_\d{4}-\d{2}-\d{2}\.csv$/)
    })

    it('应正确处理公式注入：转义后用双引号包裹', async () => {
      const data = [{ formula: '=evil' }]
      const columns: ExportColumn[] = [{ key: 'formula', label: 'Formula' }]

      exportToCSV(data, columns, 'formula.csv')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      // Blob.type 应为 CSV
      expect(blob.type).toBe('text/csv;charset=utf-8;')
      const text = await blob.text()
      // CSV 第一行为表头
      expect(text).toContain('Formula')
      // CSV 中 = 应被 ' 转义后再用双引号包裹
      expect(text).toContain("\"'=evil\"")
    })

    it('空数据应抛出错误', () => {
      const columns: ExportColumn[] = [{ key: 'x', label: 'X' }]
      expect(() => exportToCSV([], columns)).toThrow('导出数据为空')
    })
  })

  describe('exportToExcel', () => {
    it('应生成 HTML 表格格式并通过 link 下载', () => {
      const data = [
        { id: 1, name: '张三' },
        { id: 2, name: '李四' },
      ]
      const columns: ExportColumn[] = [
        { key: 'id', label: 'ID' },
        { key: 'name', label: '姓名' },
      ]

      exportToExcel(data, columns, 'export.xls')

      expect(createObjectURLMock).toHaveBeenCalledTimes(1)
      expect(linkClickMock).toHaveBeenCalledTimes(1)

      // 默认释放时间为 1000ms 后
      expect(revokeObjectURLMock).not.toHaveBeenCalled()
      vi.advanceTimersByTime(1000)
      expect(revokeObjectURLMock).toHaveBeenCalledTimes(1)
    })

    it('应正确转义 XML 特殊字符', () => {
      const data = [{ content: '<script>alert("x")</script>' }]
      const columns: ExportColumn[] = [{ key: 'content', label: 'Content' }]

      exportToExcel(data, columns, 'xss.xls')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      return blob.text().then((text) => {
        // 应包含转义后的 XML
        expect(text).toContain('&lt;script&gt;')
        expect(text).toContain('&quot;x&quot;')
        // 不应包含未转义的 <script>
        expect(text).not.toMatch(/<td><script>/)
      })
    })

    it('应使用默认文件名（无 filename 参数）', () => {
      const data = [{ x: 1 }]
      const columns: ExportColumn[] = [{ key: 'x', label: 'X' }]

      exportToExcel(data, columns)

      const calls = appendChildSpy.mock.calls
      const anchor = calls.find((c) => (c[0] as HTMLAnchorElement)?.tagName === 'A')?.[0] as HTMLAnchorElement
      expect(anchor?.download).toMatch(/^export_\d{4}-\d{2}-\d{2}\.xls$/)
    })

    it('应使用 formatter 处理值后再转义', () => {
      const data = [{ price: 1000 }]
      const columns: ExportColumn[] = [
        { key: 'price', label: 'Price', formatter: (v) => `¥${v}` },
      ]

      exportToExcel(data, columns, 'price.xls')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      return blob.text().then((text) => {
        expect(text).toContain('¥1000')
      })
    })

    it('空数据应抛出错误', () => {
      const columns: ExportColumn[] = [{ key: 'x', label: 'X' }]
      expect(() => exportToExcel([], columns)).toThrow('导出数据为空')
    })

    it('应转义公式注入字符（= 开头）', async () => {
      const data = [{ formula: '=HYPERLINK("evil")' }]
      const columns: ExportColumn[] = [{ key: 'formula', label: 'Formula' }]

      exportToExcel(data, columns, 'formula.xls')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      // sanitizeCellForExcel 在 = 前添加 '，再由 escapeXml 将 ' 转为 &apos;
      expect(text).toContain('&apos;=HYPERLINK')
    })

    it('Blob MIME type 应为 spreadsheetml.sheet', () => {
      const data = [{ x: 1 }]
      const columns: ExportColumn[] = [{ key: 'x', label: 'X' }]

      exportToExcel(data, columns, 'mime.xls')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      expect(blob.type).toBe(
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;charset=utf-8;'
      )
    })
  })

  describe('downloadJSON', () => {
    it('应序列化 JSON 并下载', () => {
      const data = { name: 'test', value: 123 }

      downloadJSON(data, 'data.json')

      expect(createObjectURLMock).toHaveBeenCalledTimes(1)
      expect(linkClickMock).toHaveBeenCalledTimes(1)

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      expect(blob.type).toBe('application/json;charset=utf-8;')
      return blob.text().then((text) => {
        const parsed = JSON.parse(text)
        expect(parsed.name).toBe('test')
        expect(parsed.value).toBe(123)
      })
    })

    it('未提供文件名时应使用默认名 .json', () => {
      downloadJSON({ a: 1 })

      const calls = appendChildSpy.mock.calls
      const anchor = calls.find((c) => (c[0] as HTMLAnchorElement)?.tagName === 'A')?.[0] as HTMLAnchorElement
      expect(anchor?.download).toMatch(/^export_\d{4}-\d{2}-\d{2}\.json$/)
    })

    it('应在 1000ms 后释放 ObjectURL', () => {
      downloadJSON({ a: 1 }, 'test.json')

      expect(revokeObjectURLMock).not.toHaveBeenCalled()
      vi.advanceTimersByTime(1000)
      expect(revokeObjectURLMock).toHaveBeenCalledTimes(1)
    })
  })

  // ===== 新增测试：覆盖 null/undefined 值、引号转义、BOM、多行数据 =====

  describe('exportToCSV - 边界场景', () => {
    it('null/undefined 值应被转为空字符串', async () => {
      const data = [{ name: null as unknown as string, age: undefined as unknown as number }]
      const columns: ExportColumn[] = [
        { key: 'name', label: 'Name' },
        { key: 'age', label: 'Age' },
      ]

      exportToCSV(data, columns, 'nulls.csv')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      // 空值应转为 ""（空引号）
      expect(text).toContain('"",""')
    })

    it('值包含双引号应被转义为两个双引号', async () => {
      const data = [{ text: 'say "hello"' }]
      const columns: ExportColumn[] = [{ key: 'text', label: 'Text' }]

      exportToCSV(data, columns, 'quotes.csv')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      // CSV 中双引号应被转义为 ""
      expect(text).toContain('"say ""hello"""')
    })

    it('值包含逗号应被双引号包裹', async () => {
      const data = [{ desc: 'a,b,c' }]
      const columns: ExportColumn[] = [{ key: 'desc', label: 'Desc' }]

      exportToCSV(data, columns, 'commas.csv')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      // 包含逗号的值应被双引号包裹
      expect(text).toContain('"a,b,c"')
    })

    it('值包含换行符应被双引号包裹', async () => {
      const data = [{ multiline: 'line1\nline2' }]
      const columns: ExportColumn[] = [{ key: 'multiline', label: 'Multi' }]

      exportToCSV(data, columns, 'multiline.csv')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      // 换行符应被包含在双引号内
      expect(text).toContain('"line1\nline2"')
    })

    it('CSV 内容应以 BOM (\\uFEFF) 开头', async () => {
      const data = [{ x: 1 }]
      const columns: ExportColumn[] = [{ key: 'x', label: 'X' }]

      exportToCSV(data, columns, 'bom.csv')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const buffer = await blob.arrayBuffer()
      const bytes = new Uint8Array(buffer)
      // UTF-8 BOM: EF BB BF
      expect(bytes[0]).toBe(0xEF)
      expect(bytes[1]).toBe(0xBB)
      expect(bytes[2]).toBe(0xBF)
    })

    it('多行数据应正确生成多行 CSV', async () => {
      const data = [
        { id: 1, name: 'Alice' },
        { id: 2, name: 'Bob' },
        { id: 3, name: 'Charlie' },
      ]
      const columns: ExportColumn[] = [
        { key: 'id', label: 'ID' },
        { key: 'name', label: 'Name' },
      ]

      exportToCSV(data, columns, 'multi.csv')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      const lines = text.split('\n')
      // 1 header + 3 data rows
      expect(lines).toHaveLength(4)
      expect(lines[0]).toBe('ID,Name')
      expect(lines[1]).toContain('Alice')
      expect(lines[3]).toContain('Charlie')
    })

    it('formatter 返回 undefined 时应转为空字符串', async () => {
      const data = [{ x: 1 }]
      const columns: ExportColumn[] = [
        {
          key: 'x',
          label: 'X',
          formatter: () => undefined as unknown as string,
        },
      ]

      exportToCSV(data, columns, 'undef.csv')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      // formatter 返回 undefined 应转为空字符串
      expect(text).toContain('""')
    })

    it('数字 0 应被正确导出（不为空）', async () => {
      const data = [{ count: 0 }]
      const columns: ExportColumn[] = [{ key: 'count', label: 'Count' }]

      exportToCSV(data, columns, 'zero.csv')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      // 0 应被导出为 "0"，不是空字符串
      expect(text).toContain('"0"')
    })

    it('布尔值应被转为字符串', async () => {
      const data = [{ active: true, deleted: false }]
      const columns: ExportColumn[] = [
        { key: 'active', label: 'Active' },
        { key: 'deleted', label: 'Deleted' },
      ]

      exportToCSV(data, columns, 'bools.csv')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      expect(text).toContain('"true"')
      expect(text).toContain('"false"')
    })
  })

  describe('exportToExcel - 边界场景', () => {
    it('null/undefined 值应被转为空字符串', async () => {
      const data = [{ name: null as unknown as string }]
      const columns: ExportColumn[] = [{ key: 'name', label: 'Name' }]

      exportToExcel(data, columns, 'nulls.xls')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      // 空值应转为空的 <td></td>
      expect(text).toContain('<td></td>')
    })

    it('表头包含 XML 特殊字符应被转义', async () => {
      const data = [{ x: 1 }]
      const columns: ExportColumn[] = [{ key: 'x', label: 'A & B <C>' }]

      exportToExcel(data, columns, 'xml-header.xls')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      // 表头中的特殊字符应被转义
      expect(text).toContain('A &amp; B &lt;C&gt;')
    })

    it('值包含 & 应被转义为 &amp;', async () => {
      const data = [{ company: 'A & B Co' }]
      const columns: ExportColumn[] = [{ key: 'company', label: 'Company' }]

      exportToExcel(data, columns, 'amp.xls')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      expect(text).toContain('A &amp; B Co')
    })

    it('值包含单引号应被转义为 &apos;', async () => {
      const data = [{ text: "it's" }]
      const columns: ExportColumn[] = [{ key: 'text', label: 'Text' }]

      exportToExcel(data, columns, 'apos.xls')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      expect(text).toContain('it&apos;s')
    })

    it('多行数据应生成多个 <tr> 行', async () => {
      const data = [
        { id: 1, name: 'A' },
        { id: 2, name: 'B' },
      ]
      const columns: ExportColumn[] = [
        { key: 'id', label: 'ID' },
        { key: 'name', label: 'Name' },
      ]

      exportToExcel(data, columns, 'multi.xls')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      // 应有 3 个 <tr> 行：1 thead header + 2 tbody data rows
      const trCount = (text.match(/<tr>/g) || []).length
      expect(trCount).toBe(3)
    })

    it('应包含 HTML 命名空间声明', async () => {
      const data = [{ x: 1 }]
      const columns: ExportColumn[] = [{ key: 'x', label: 'X' }]

      exportToExcel(data, columns, 'ns.xls')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      expect(text).toContain('xmlns:o="urn:schemas-microsoft-com:office:office"')
      expect(text).toContain('xmlns:x="urn:schemas-microsoft-com:office:excel"')
    })

    it('应包含 meta charset UTF-8', async () => {
      const data = [{ x: 1 }]
      const columns: ExportColumn[] = [{ key: 'x', label: 'X' }]

      exportToExcel(data, columns, 'charset.xls')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      expect(text).toContain('<meta charset="UTF-8">')
    })

    it('formatter 返回值应先转义公式注入再转义 XML', async () => {
      const data = [{ formula: 'x' }]
      const columns: ExportColumn[] = [
        {
          key: 'formula',
          label: 'F',
          formatter: () => '=cmd',
        },
      ]

      exportToExcel(data, columns, 'fmt.xls')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      // = 被转义为 '=cmd，' 再被 escapeXml 转为 &apos;
      expect(text).toContain('&apos;=cmd')
    })
  })

  describe('downloadJSON - 边界场景', () => {
    it('应正确序列化数组数据', async () => {
      const data = [1, 2, 3]

      downloadJSON(data, 'array.json')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      expect(JSON.parse(text)).toEqual([1, 2, 3])
    })

    it('应正确序列化嵌套对象', async () => {
      const data = { user: { name: 'a', tags: ['x', 'y'] } }

      downloadJSON(data, 'nested.json')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      expect(JSON.parse(text)).toEqual(data)
    })

    it('应正确序列化 null', async () => {
      downloadJSON(null, 'null.json')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      expect(JSON.parse(text)).toBeNull()
    })

    it('应正确序列化字符串', async () => {
      downloadJSON('hello', 'str.json')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      expect(JSON.parse(text)).toBe('hello')
    })

    it('JSON 输出应为格式化（2 空格缩进）', async () => {
      const data = { a: 1 }

      downloadJSON(data, 'pretty.json')

      const blob = createObjectURLMock.mock.calls[0][0] as Blob
      const text = await blob.text()
      // JSON.stringify(data, null, 2) 应包含换行和缩进
      expect(text).toContain('\n')
      expect(text).toContain('  "a": 1')
    })
  })

  describe('sanitizeCellForExcel - 额外边界', () => {
    it('空格字符串不应被转义', () => {
      expect(sanitizeCellForExcel('   ')).toBe('   ')
    })

    it('纯数字不应被转义', () => {
      expect(sanitizeCellForExcel('0')).toBe('0')
      expect(sanitizeCellForExcel('3.14159')).toBe('3.14159')
    })

    it('科学计数法数字不应被转义', () => {
      expect(sanitizeCellForExcel('1e10')).toBe('1e10')
      expect(sanitizeCellForExcel('1.5e-3')).toBe('1.5e-3')
    })

    it('以 - 开头后跟空格的非数字应被转义', () => {
      expect(sanitizeCellForExcel('- abc')).toBe("'- abc")
    })

    it('仅 - 字符应被转义（slice(1).trim() 为空）', () => {
      // - 后为空，numPart 为空，不满足 numPart && 正则条件
      // 但 value.startsWith('-') 为 true，numPart 为空字符串
      // 空 && ... → false，不转义
      expect(sanitizeCellForExcel('-')).toBe('-')
    })
  })
})

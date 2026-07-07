import i18n from '@/i18n'

const t = i18n.global.t.bind(i18n.global)

export interface ExportColumn<T = unknown> {
  key: string
  label: string
  formatter?: (value: unknown, row: T) => string
}

/**
 * FE-003 修复：转义 Excel/CSV 公式注入危险字符。
 *
 * 当单元格值以 =, +, -, @, \t, \r 开头时，Excel 会将其解释为公式，
 * 可能导致公式注入攻击。通过在前面添加单引号 ' 强制 Excel 将其作为文本处理。
 * 对 "-" 开头的值，仅当不是合法数字时才转义（避免影响负数导出）。
 */
export function sanitizeCellForExcel(value: string): string {
  if (!value) return value
  const dangerousPrefixes = ['=', '+', '@', '\t', '\r']
  if (dangerousPrefixes.some((p) => value.startsWith(p))) {
    return "'" + value
  }
  if (value.startsWith('-')) {
    const numPart = value.slice(1).trim()
    if (numPart && !/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(numPart)) {
      return "'" + value
    }
  }
  return value
}

export function exportToCSV<T extends Record<string, unknown>>(
  data: T[],
  columns: ExportColumn<T>[],
  filename?: string
): void {
  if (!data.length) {
    throw new Error(t('exportUtils.emptyData'))
  }

  const headers = columns.map((col) => col.label)
  const rows = data.map((row) =>
    columns
      .map((col) => {
        const rawValue = row[col.key]
        const value = col.formatter ? col.formatter(rawValue, row) : rawValue
        // FE-003 修复：先转义公式注入，再转义 CSV 引号
        const sanitized = sanitizeCellForExcel(String(value ?? ''))
        return `"${sanitized.replace(/"/g, '""')}"`
      })
      .join(',')
  )

  const csvContent = [headers.join(','), ...rows].join('\n')
  const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' })

  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename || `export_${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  // M-29 修复：延迟释放 ObjectURL，避免浏览器尚未开始下载就被回收
  const csvUrl = link.href
  setTimeout(() => URL.revokeObjectURL(csvUrl), 1000)
}

export function exportToExcel<T extends Record<string, unknown>>(
  data: T[],
  columns: ExportColumn<T>[],
  filename?: string
): void {
  if (!data.length) {
    throw new Error(t('exportUtils.emptyData'))
  }

  const headers = columns.map((col) => `<th>${escapeXml(col.label)}</th>`).join('')
  const rows = data
    .map(
      (row) =>
        '<tr>' +
        columns
          .map((col) => {
            const rawValue = row[col.key]
            const value = col.formatter ? col.formatter(rawValue, row) : rawValue
            // FE-003 修复：先转义公式注入，再转义 XML
            const sanitized = sanitizeCellForExcel(String(value ?? ''))
            return `<td>${escapeXml(sanitized)}</td>`
          })
          .join('') +
        '</tr>'
    )
    .join('')

  const html = `
    <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel">
      <head><meta charset="UTF-8"></head>
      <body>
        <table>
          <thead><tr>${headers}</tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </body>
    </html>
  `

  // L-09 修复：使用更准确的 MIME type，避免某些 Excel 版本打开时警告
  // 注意：这是 HTML 表格伪装为 Excel 格式，非真正的 .xlsx 文件
  // 如需真正的 Excel 格式，建议引入 SheetJS (xlsx) 库
  const blob = new Blob([html], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;charset=utf-8;' })

  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename || `export_${new Date().toISOString().slice(0, 10)}.xls`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  // M-29 修复：延迟释放 ObjectURL，避免浏览器尚未开始下载就被回收
  const excelUrl = link.href
  setTimeout(() => URL.revokeObjectURL(excelUrl), 1000)
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

export function downloadJSON(data: unknown, filename?: string): void {
  const jsonStr = JSON.stringify(data, null, 2)
  const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8;' })

  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename || `export_${new Date().toISOString().slice(0, 10)}.json`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  // M-29 修复：延迟释放 ObjectURL，避免浏览器尚未开始下载就被回收
  const jsonUrl = link.href
  setTimeout(() => URL.revokeObjectURL(jsonUrl), 1000)
}

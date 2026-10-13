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

/**
 * P1-29 修复：CSV 单元格序列化 —— 表头与数据单元格走同一条转义链。
 *
 * FE-003 只给**数据单元格**做了公式注入转义，表头 `headers.join(',')` 是裸串：
 *   1. 公式注入：列名以 `=`/`+`/`-`/`@` 开头时 Excel 同样会当公式执行
 *      （表头来自 i18n 文案与后端字段标签，后者部分可由管理员配置）。
 *   2. CSV 结构破坏：列名含逗号/引号/换行时不做引号包裹会整体错列。
 * 数据行早就做了「先 sanitize 再引号转义」，表头漏了同一件事。
 */
function toCsvCell(value: string): string {
  const sanitized = sanitizeCellForExcel(value)
  return `"${sanitized.replace(/"/g, '""')}"`
}

/** P2-32 余量：CSV 单元格 SSOT 的公开别名，供各列表页内联转义链改调。 */
export const csvEscape = toCsvCell

/**
 * P2-32 SSOT：Blob 下载的唯一入口。
 *
 * 实测（backend/scripts/audit_ssot_duplication.py）旧有11 处手写下载链路，
 * 分为两种变体，其中 **4 处仍是同步 revoke**（TaskProgressNotification:164、
 * AdminReportsPage:53、GdprTab:210、UserReportsPage:61）—— 正是 M-29 修复过
 * 的缺陷（ObjectURL 在浏览器开始下载前被回收，下载静默失败）在这些调用点
 * 上从未被修复。这是「同模式复制 N 份后各自漂移」的教科书案例。
 *
 * 本函数把 revoke 时机固定为**延迟 1000ms**，消除变体；同时收敛
 * appendChild / removeChild 细节（部分旧调用点漏了，导致 Firefox 下
 * 脱离文档的<a> click 可能不触发下载）。
 *
 * @param blob 待下载内容
 * @param filename 建议文件名（不含路径，浏览器会自行处理）
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  // M-29 修复：延迟释放 ObjectURL，避免浏览器尚未开始下载就被回收。
  // 此前只有exportUtils 内 3 处这样做，11 处调用点中有 4 处仍是同步 revoke。
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function exportToCSV<T extends Record<string, unknown>>(
  data: T[],
  columns: ExportColumn<T>[],
  filename?: string
): void {
  if (!data.length) {
    throw new Error(t('exportUtils.emptyData'))
  }

  const headers = columns.map((col) => toCsvCell(col.label))
  const rows = data.map((row) =>
    columns
      .map((col) => {
        const rawValue = row[col.key]
        const value = col.formatter ? col.formatter(rawValue, row) : rawValue
        // FE-003 修复：先转义公式注入，再转义 CSV 引号
        return toCsvCell(String(value ?? ''))
      })
      .join(',')
  )

  const csvContent = [headers.join(','), ...rows].join('\n')
  const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' })
  downloadBlob(blob, filename || `export_${new Date().toISOString().slice(0, 10)}.csv`)
}

export function exportToExcel<T extends Record<string, unknown>>(
  data: T[],
  columns: ExportColumn<T>[],
  filename?: string
): void {
  if (!data.length) {
    throw new Error(t('exportUtils.emptyData'))
  }

  // P1-29 修复：表头与数据单元格同样先过 sanitizeCellForExcel 再 escapeXml。
  // FE-003 原先只转义数据单元格，表头漏了同一件事（Excel 打开 HTML 表格时
  // 同样会把 `=`/`+`/`-`/`@` 开头的内容当公式执行）。
  const headers = columns
    .map((col) => `<th>${escapeXml(sanitizeCellForExcel(col.label))}</th>`)
    .join('')
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
  downloadBlob(blob, filename || `export_${new Date().toISOString().slice(0, 10)}.xls`)
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
  downloadBlob(blob, filename || `export_${new Date().toISOString().slice(0, 10)}.json`)
}

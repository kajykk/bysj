export function formatLabel(format: 'pdf' | 'csv' | 'json'): string {
  return { pdf: 'PDF 报告', csv: 'CSV 数据', json: 'JSON 数据' }[format]
}

export function buildJsonBlob(data: unknown): Blob {
  return new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
}

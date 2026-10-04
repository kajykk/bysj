import request, { dedupedGet, requestData } from './request'

export const userFileApi = {
  exportRiskPdf: (days = 90) => dedupedGet('/user/risk/export', { params: { format: 'pdf', days }, responseType: 'blob' }),

  exportRiskData: (format: 'json' | 'csv' | 'pdf', days = 90) => dedupedGet('/user/risk/export', { params: { format, days }, responseType: 'blob' }),

  uploadFile: (formData: FormData, category?: string) => {
    const params = category ? { category } : {}
    // C-FE-1 修复：删除手动设置的 'Content-Type': 'multipart/form-data'，
    // 让浏览器自动生成带 boundary 的 Content-Type，否则后端无法解析请求体
    return requestData<{ url: string; filename: string; original_name: string; size: number; content_type: string }>(
      request.post('/user/upload', formData, { params })
    )
  },

  /**
   * AUDIT-2026-10-01（决策三 P6）：批量上传（POST /user/upload/batch）。
   *
   * 后端单次上限 10 个文件（超出返回 400），单文件失败只影响该项结果（带 error 字段），
   * 因此调用方应逐项检查 items，而不是只看 failed 计数。
   */
  uploadFiles: (formData: FormData, category?: string) => {
    const params = category ? { category } : {}
    return requestData<UploadBatchResult>(request.post('/user/upload/batch', formData, { params }))
  },
}

export interface UploadBatchItem {
  url?: string
  filename?: string
  original_name?: string
  size?: number
  content_type?: string
  /** 单文件失败时由后端填充；成功项不含此字段 */
  error?: string
  [key: string]: unknown
}

export interface UploadBatchResult {
  items: UploadBatchItem[] | null
  count: number | null
  total: number | null
  failed: number | null
}

import request, { requestData } from './request'

export const userFileApi = {
  exportRiskPdf: (days = 90) => request.get('/user/risk/export', { params: { format: 'pdf', days }, responseType: 'blob' }),

  exportRiskData: (format: 'json' | 'csv' | 'pdf', days = 90) => request.get('/user/risk/export', { params: { format, days }, responseType: 'blob' }),

  uploadFile: (formData: FormData, category?: string) => {
    const params = category ? { category } : {}
    // C-FE-1 修复：删除手动设置的 'Content-Type': 'multipart/form-data'，
    // 让浏览器自动生成带 boundary 的 Content-Type，否则后端无法解析请求体
    return requestData<{ url: string; filename: string; original_name: string; size: number; content_type: string }>(
      request.post('/user/upload', formData, { params })
    )
  },
}

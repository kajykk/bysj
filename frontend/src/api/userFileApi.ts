import request, { requestData } from './request'

export const userFileApi = {
  exportRiskPdf: (days = 90) => request.get('/user/risk/export', { params: { format: 'pdf', days }, responseType: 'blob' }),

  exportRiskData: (format: 'json' | 'csv' | 'pdf', days = 90) => request.get('/user/risk/export', { params: { format, days }, responseType: 'blob' }),

  uploadFile: (formData: FormData, category?: string) => {
    const params = category ? { category } : {}
    return requestData<{ url: string; filename: string; original_name: string; size: number; content_type: string }>(
      request.post('/user/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' }, params })
    )
  },
}

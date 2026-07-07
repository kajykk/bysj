import request, { requestData } from './request'

/** 账户匿名化结果 (后端 GDPRService.anonymize_user 返回) */
export interface GdprDeleteResult {
  user_id: number
  anonymized_at: string
  original_email_masked: string
  contacts_anonymized: number
  sessions_revoked: number
  risk_assessments_deleted: number
  legal_records_retained: boolean
  warning: string
}

export const gdprApi = {
  // 导出个人数据 (GDPR Article 15 / 20) - 返回 blob 流，由调用方触发下载
  // 后端返回 StreamingResponse (application/json, attachment)，不经过 ok() 包装
  exportUserData: () => request.get('/user/gdpr/export', { responseType: 'blob' }),

  // 匿名化账户 (GDPR Article 17) - 需密码 + 显式确认 (confirm: true)
  // 后端返回 ok(result)，经 requestData 解包
  deleteAccount: (payload: { password: string; confirm: boolean }) =>
    requestData<GdprDeleteResult>(request.post('/user/gdpr/delete', payload)),
}

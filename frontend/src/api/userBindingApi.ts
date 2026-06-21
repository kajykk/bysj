import request, { requestData } from './request'
import type { UserBindingInfo } from './userTypes'

export interface BindCounselorResult {
  binding_id: number
  counselor_id: number
  counselor_name: string
  counselor_email: string | null
  bound_at: string
  status: UserBindingInfo['status']
  bind_code_status: UserBindingInfo['bind_code_status']
}

export const userBindingApi = {
  getUserBinding: () => requestData<UserBindingInfo | null>(request.get('/user/data/binding')),
  bindCounselor: (bindCode: string) => requestData<BindCounselorResult>(request.post('/user/data/binding', { bind_code: bindCode })),
  unbindCounselor: () => requestData<{ message: string }>(request.delete('/user/data/binding')),
}

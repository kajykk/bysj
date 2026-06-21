import { describe, expect, it } from 'vitest'
import { ROUTE_PERMISSIONS } from './routeAccess'

describe('ROUTE_PERMISSIONS', () => {
  it('groups user routes consistently', () => {
    expect(ROUTE_PERMISSIONS.userWarnings).toEqual(['user.warning.read', 'user.warning.track'])
    expect(ROUTE_PERMISSIONS.userAssessments).toEqual(['user.assessment.read'])
  })

  it('groups counselor routes consistently', () => {
    expect(ROUTE_PERMISSIONS.counselorWarnings).toEqual([
      'counselor.warning.handle',
      'counselor.warning.ignore',
      'counselor.warning.batch'
    ])
    expect(ROUTE_PERMISSIONS.counselorConsultation).toEqual(['counselor.user.consultation.view'])
  })

  it('groups admin routes consistently', () => {
    expect(ROUTE_PERMISSIONS.adminOperationLogs).toEqual([
      'admin.operation_log.view',
      'admin.operation_log.filter',
      'admin.operation_log.audit'
    ])
  })
})

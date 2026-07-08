import { describe, it, expect } from 'vitest'
import { PAGE_PERMISSIONS, ROLE_PERMISSIONS } from './permissions'
import { ROUTE_PERMISSIONS } from './routeAccess'

describe('alignment permissions', () => {
  it('新增 5 个 PAGE_PERMISSIONS 键', () => {
    expect(PAGE_PERMISSIONS.userReports).toEqual(['user.export.risk'])
    expect(PAGE_PERMISSIONS.adminReports).toEqual(['admin.predict.audit'])
    expect(PAGE_PERMISSIONS.adminObservability).toEqual(['admin.alerts.view'])
    expect(PAGE_PERMISSIONS.adminMonitoring).toEqual(['admin.predict.audit'])
    expect(PAGE_PERMISSIONS.adminCanary).toEqual(['admin.predict.audit'])
  })
  it('ROUTE_PERMISSIONS 含 5 新键', () => {
    expect(ROUTE_PERMISSIONS.userReports).toContain('user.export.risk')
    expect(ROUTE_PERMISSIONS.adminReports).toContain('admin.predict.audit')
    expect(ROUTE_PERMISSIONS.adminObservability).toContain('admin.alerts.view')
    expect(ROUTE_PERMISSIONS.adminMonitoring).toContain('admin.predict.audit')
    expect(ROUTE_PERMISSIONS.adminCanary).toContain('admin.predict.audit')
  })
  it('admin 角色显式含所有新权限', () => {
    const admin = ROLE_PERMISSIONS.admin
    expect(admin).toContain('user.export.risk')
    expect(admin).toContain('admin.predict.audit')
    expect(admin).toContain('admin.alerts.view')
  })
  it('user 角色含 user.export.risk', () => {
    expect(ROLE_PERMISSIONS.user).toContain('user.export.risk')
  })
})

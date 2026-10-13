import { describe, expect, it } from 'vitest'
import {
  USER_ROLE_ADMIN,
  USER_ROLE_COUNSELOR,
  USER_ROLE_SUPER_ADMIN,
  USER_ROLE_USER,
  isAdminRole,
  isCounselorRole,
  isKnownRole,
  isStaffRole,
  isUserRole,
} from '@/utils/roles'

describe('P2-37 role helpers (SSOT behavior)', () => {
  it('constants match backend contracts USER_ROLE_*', () => {
    expect([USER_ROLE_USER, USER_ROLE_COUNSELOR, USER_ROLE_ADMIN, USER_ROLE_SUPER_ADMIN]).toEqual([
      'user',
      'counselor',
      'admin',
      'super_admin',
    ])
  })
  it('isAdminRole: admin + super_admin only', () => {
    expect(isAdminRole('admin')).toBe(true)
    expect(isAdminRole('super_admin')).toBe(true)
    expect(isAdminRole('counselor')).toBe(false)
    expect(isAdminRole('user')).toBe(false)
    expect(isAdminRole('')).toBe(false)
    expect(isAdminRole(undefined)).toBe(false)
  })
  it('isStaffRole: admin + counselor only', () => {
    expect(isStaffRole('admin')).toBe(true)
    expect(isStaffRole('counselor')).toBe(true)
    expect(isStaffRole('super_admin')).toBe(false)
    expect(isStaffRole('user')).toBe(false)
  })
  it('isKnownRole rejects unknown/empty', () => {
    expect(isKnownRole('root')).toBe(false)
    expect(isKnownRole('')).toBe(false)
    expect(isKnownRole('user')).toBe(true)
    expect(isCounselorRole('counselor')).toBe(true)
    expect(isUserRole('user')).toBe(true)
  })
})

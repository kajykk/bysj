import { describe, it, expect } from 'vitest'
import {
  WARNING_RISK_LEVELS,
  normalizeWarningRiskLevel,
  getWarningRiskLevelLabel,
  getWarningRiskLevelTagType,
  formatHandledBy,
  isWarningHandled
} from './warning'

describe('warning - 风险等级归一化 (M-FIX-001)', () => {
  it('数值输入原样映射 (0-4)', () => {
    expect(normalizeWarningRiskLevel(0)).toBe(0)
    expect(normalizeWarningRiskLevel(2)).toBe(2)
    expect(normalizeWarningRiskLevel(4)).toBe(4)
  })

  it('字符串标签映射为数值 (normalize_risk_level)', () => {
    expect(normalizeWarningRiskLevel('none')).toBe(0)
    expect(normalizeWarningRiskLevel('low')).toBe(1)
    expect(normalizeWarningRiskLevel('medium')).toBe(2)
    expect(normalizeWarningRiskLevel('high')).toBe(3)
    expect(normalizeWarningRiskLevel('critical')).toBe(4)
  })

  it('字符串映射大小写不敏感并忽略空白', () => {
    expect(normalizeWarningRiskLevel('HIGH')).toBe(3)
    expect(normalizeWarningRiskLevel('  Low  ')).toBe(1)
  })

  it('未知/非法输入返回 -1', () => {
    expect(normalizeWarningRiskLevel('unknown')).toBe(-1)
    expect(normalizeWarningRiskLevel('foo')).toBe(-1)
    expect(normalizeWarningRiskLevel(null)).toBe(-1)
    expect(normalizeWarningRiskLevel(undefined)).toBe(-1)
    expect(normalizeWarningRiskLevel({})).toBe(-1)
  })

  it('数值超出范围被钳制', () => {
    expect(normalizeWarningRiskLevel(99)).toBe(4)
    expect(normalizeWarningRiskLevel(-99)).toBe(-1)
  })

  it('WARNING_RISK_LEVELS 覆盖全部合法等级', () => {
    expect(WARNING_RISK_LEVELS).toEqual([0, 1, 2, 3, 4])
  })

  it('getWarningRiskLevelTagType 兼容字符串与数值', () => {
    expect(getWarningRiskLevelTagType('low')).toBe('success')
    expect(getWarningRiskLevelTagType(1)).toBe('success')
    expect(getWarningRiskLevelTagType(4)).toBe('danger')
    expect(getWarningRiskLevelTagType(0)).toBe('info')
  })

  it('getWarningRiskLevelLabel 兼容字符串与数值', () => {
    expect(getWarningRiskLevelLabel('high')).toBe(getWarningRiskLevelLabel(3))
    expect(getWarningRiskLevelLabel('critical')).toBe(getWarningRiskLevelLabel(4))
  })
})

describe('warning - isWarningHandled 状态判定', () => {
  it('永久态/升级态视为已处理', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(isWarningHandled({ status: 'pending' } as any)).toBe(false)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(isWarningHandled({ status: 'handled' } as any)).toBe(true)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(isWarningHandled({ status: 'ignored' } as any)).toBe(true)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(isWarningHandled({ status: 'escalated' } as any)).toBe(true)
  })
})

describe('warning - formatHandledBy 展示归一化 (M-FIX-007)', () => {
  it('咨询师端 counselor#N 字符串剥离前缀', () => {
    expect(formatHandledBy('counselor#5')).toBe('5')
    expect(formatHandledBy('counselor#12')).toBe('12')
  })

  it('用户端数值原样返回', () => {
    expect(formatHandledBy(7)).toBe('7')
  })

  it('空值返回 fallback', () => {
    expect(formatHandledBy(null)).toBe('—')
    expect(formatHandledBy(undefined)).toBe('—')
    expect(formatHandledBy('')).toBe('—')
  })

  it('非 counselor# 前缀字符串原样返回', () => {
    expect(formatHandledBy('admin#1')).toBe('admin#1')
    expect(formatHandledBy('ops_2')).toBe('ops_2')
  })
})
import { describe, it, expect } from 'vitest'
import {
  formatDate,
  formatRelativeTime,
  formatNumber,
  formatPercent,
  formatFileSize,
  truncateText
} from './formatUtils'

describe('formatUtils - 6.2.2 格式化工具函数', () => {
  it('formatDate 应正确格式化日期', () => {
    const date = new Date('2026-04-27T15:30:45')

    expect(formatDate(date, 'YYYY-MM-DD')).toBe('2026-04-27')
    expect(formatDate(date, 'HH:mm:ss')).toBe('15:30:45')
    expect(formatDate(date, 'YYYY-MM-DD HH:mm:ss')).toBe('2026-04-27 15:30:45')
  })

  it('formatDate 应处理空值', () => {
    expect(formatDate(null)).toBe('-')
    expect(formatDate(undefined)).toBe('-')
    expect(formatDate('')).toBe('-')
  })

  it('formatRelativeTime 应返回相对时间描述', () => {
    const now = new Date()
    const oneMinuteAgo = new Date(now.getTime() - 60 * 1000)
    const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000)
    const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000)

    expect(formatRelativeTime(oneMinuteAgo)).toBe('1分钟前')
    expect(formatRelativeTime(oneHourAgo)).toBe('1小时前')
    expect(formatRelativeTime(oneDayAgo)).toBe('1天前')
  })

  it('formatNumber 应添加千分位分隔符', () => {
    expect(formatNumber(1234567)).toBe('1,234,567')
    expect(formatNumber(1234567.89, 2)).toBe('1,234,567.89')
    expect(formatNumber(null)).toBe('-')
  })

  it('formatPercent 应正确格式化百分比', () => {
    expect(formatPercent(0.8567)).toBe('85.67%')
    expect(formatPercent(0.8567, 1)).toBe('85.7%')
    expect(formatPercent(null)).toBe('-')
  })

  it('formatFileSize 应正确格式化文件大小', () => {
    expect(formatFileSize(1024)).toBe('1.00 KB')
    expect(formatFileSize(1024 * 1024)).toBe('1.00 MB')
    expect(formatFileSize(1024 * 1024 * 1024)).toBe('1.00 GB')
    expect(formatFileSize(512)).toBe('512.00 B')
  })

  it('truncateText 应正确截断文本', () => {
    expect(truncateText('Hello World', 5)).toBe('Hello...')
    expect(truncateText('Hi', 5)).toBe('Hi')
    expect(truncateText(null, 5)).toBe('')
  })
})

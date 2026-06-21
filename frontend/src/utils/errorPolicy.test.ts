import { describe, expect, it } from 'vitest'
import { normalizeHttpError } from '@/utils/errorPolicy'

const mockAxiosError = (status: number, detail: string) => ({
  isAxiosError: true,
  message: detail,
  response: { status, data: { detail } }
})

describe('error policy', () => {
  it('normalizes 401 as warning without retry', () => {
    const normalized = normalizeHttpError(mockAxiosError(401, 'token expired') as never, 'fallback')
    expect(normalized.status).toBe(401)
    expect(normalized.level).toBe('warning')
    expect(normalized.showRetry).toBe(false)
  })

  it('normalizes 422 as warning without retry', () => {
    const normalized = normalizeHttpError(mockAxiosError(422, 'invalid') as never, 'fallback')
    expect(normalized.status).toBe(422)
    expect(normalized.level).toBe('warning')
    expect(normalized.showRetry).toBe(false)
  })

  it('normalizes 500 as error with retry', () => {
    const normalized = normalizeHttpError(mockAxiosError(500, 'server error') as never, 'fallback')
    expect(normalized.status).toBe(500)
    expect(normalized.level).toBe('error')
    expect(normalized.showRetry).toBe(true)
  })
})

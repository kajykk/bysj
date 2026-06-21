import { describe, expect, it } from 'vitest'
import { normalizeHttpErrorInfo } from './httpError'

const mockAxiosError = (status: number, payload = {}, message = 'axios failure') => ({
  isAxiosError: true,
  message,
  response: { status, data: payload }
})

describe('normalizeHttpErrorInfo', () => {
  it('uses detail first then message then fallback', () => {
    expect(normalizeHttpErrorInfo(mockAxiosError(400, { detail: 'detail' }), 'fallback')).toEqual({ status: 400, detail: 'detail' })
    expect(normalizeHttpErrorInfo(mockAxiosError(400, { message: 'message' }), 'fallback')).toEqual({ status: 400, detail: 'message' })
    expect(normalizeHttpErrorInfo(mockAxiosError(400, {}), 'fallback')).toEqual({ status: 400, detail: 'axios failure' })
  })

  it('falls back for non-axios errors', () => {
    expect(normalizeHttpErrorInfo(new Error('oops'), 'fallback')).toEqual({ status: 0, detail: 'oops' })
  })
})

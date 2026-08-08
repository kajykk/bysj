import { describe, expect, it } from 'vitest'
import { getNetworkErrorMessage, normalizeHttpErrorInfo } from './httpError'

describe('httpError - normalizeHttpErrorInfo', () => {
  it('有响应时提取 status 与 detail', () => {
    const error: any = new Error('Request failed with status 403')
    error.response = { status: 403, data: { detail: '无权限' } }
    expect(normalizeHttpErrorInfo(error, 'fallback')).toEqual({ status: 403, detail: '无权限' })
  })

  it('detail 缺失时回退到 error.message', () => {
    const error: any = new Error('Network Error')
    expect(normalizeHttpErrorInfo(error, 'fallback')).toEqual({ status: 0, detail: 'Network Error' })
  })

  it('全部缺失时使用调用方 fallback', () => {
    const error: any = new Error('')
    expect(normalizeHttpErrorInfo(error, '请求失败')).toEqual({ status: 0, detail: '请求失败' })
  })
})

describe('getNetworkErrorMessage (ISS-106)', () => {
  it('超时（ECONNABORTED）映射为中文提示', () => {
    const error: any = new Error('timeout of 60000ms exceeded')
    error.code = 'ECONNABORTED'
    expect(getNetworkErrorMessage(error)).toBe('请求超时，请重试')
  })

  it('axios 1.x 的 ERR_NETWORK 映射为断网提示', () => {
    const error: any = new Error('Network Error')
    error.code = 'ERR_NETWORK'
    expect(getNetworkErrorMessage(error)).toBe('网络连接失败，请检查网络设置')
  })

  it('连接被拒绝（ECONNREFUSED）映射为连接异常', () => {
    const error: any = new Error('connect ECONNREFUSED 127.0.0.1:8000')
    error.code = 'ECONNREFUSED'
    expect(getNetworkErrorMessage(error)).toBe('网络连接异常，请稍后重试')
  })

  it('未知错误返回 null（由调用方回退通用提示）', () => {
    expect(getNetworkErrorMessage(new Error('unrelated'))).toBeNull()
    expect(getNetworkErrorMessage('not an error object')).toBeNull()
    expect(getNetworkErrorMessage(null)).toBeNull()
  })

  it('canceled 请求不命中网络错误映射', () => {
    const error: any = new Error('canceled')
    error.code = 'ERR_CANCELED'
    expect(getNetworkErrorMessage(error)).toBeNull()
  })
})
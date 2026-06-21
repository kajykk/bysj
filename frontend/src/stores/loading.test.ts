import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useLoadingStore } from './loading'

describe('loading store - 7.2.1 全局加载状态管理', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('初始状态应为未加载', () => {
    const store = useLoadingStore()
    expect(store.globalLoading).toBe(false)
    expect(store.loadingCount).toBe(0)
    expect(store.isLoading).toBe(false)
  })

  it('startLoading 应增加计数并设置加载状态', () => {
    const store = useLoadingStore()
    store.startLoading('正在加载数据')

    expect(store.loadingCount).toBe(1)
    expect(store.globalLoading).toBe(true)
    expect(store.loadingText).toBe('正在加载数据')
    expect(store.isLoading).toBe(true)
  })

  it('多次 startLoading 应累加计数', () => {
    const store = useLoadingStore()
    store.startLoading()
    store.startLoading()
    store.startLoading()

    expect(store.loadingCount).toBe(3)
    expect(store.isLoading).toBe(true)
  })

  it('stopLoading 应减少计数', () => {
    const store = useLoadingStore()
    store.startLoading()
    store.startLoading()
    store.stopLoading()

    expect(store.loadingCount).toBe(1)
    expect(store.isLoading).toBe(true)
  })

  it('stopLoading 到 0 应重置状态', () => {
    const store = useLoadingStore()
    store.startLoading('自定义文本')
    store.stopLoading()

    expect(store.loadingCount).toBe(0)
    expect(store.globalLoading).toBe(false)
    expect(store.loadingText).toBe('加载中...')
    expect(store.isLoading).toBe(false)
  })

  it('setGlobalLoading 应直接设置状态', () => {
    const store = useLoadingStore()
    store.setGlobalLoading(true, '全局加载')

    expect(store.globalLoading).toBe(true)
    expect(store.loadingText).toBe('全局加载')
    expect(store.isLoading).toBe(true)
  })
})

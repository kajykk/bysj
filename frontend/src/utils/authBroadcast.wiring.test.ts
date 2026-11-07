import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * ROUND_35 / M-18：跨标签页 token 广播的**接线**闸门。
 *
 * auth.test.ts 等既有测试验证 store 行为，但验证不了「广播函数是否真的被
 * 登录/续期/登出/401 刷新调用」——ROUND_34 之前正是「监听注册好了、广播方
 * 没接线」。这里剥掉注释后按函数块断言真实调用形态，配合 mutate_round35.py
 * 对每处调用做一次变异：删掉调用必须让断言变红。
 */

const read = (rel: string) => readFileSync(resolve(__dirname, '..', rel), 'utf8')
const stripComments = (s: string) =>
  s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')

function block(src: string, marker: string, length = 500): string {
  const start = src.indexOf(marker)
  expect(start).toBeGreaterThan(-1)
  return src.slice(start, start + length)
}

describe('M-18 广播接线', () => {
  it('auth.ts 与 request.ts 都复用同一个广播实现', () => {
    const auth = stripComments(read('stores/auth.ts'))
    const request = stripComments(read('api/request.ts'))
    expect(auth).toContain("from '@/utils/authBroadcast'")
    expect(request).toContain("from '@/utils/authBroadcast'")
    // 单一实现本身必须同时具备同标签页与跨标签页两种投递
    const impl = stripComments(readFileSync(resolve(__dirname, 'authBroadcast.ts'), 'utf8'))
    expect(impl).toContain('CustomEvent')
    expect(impl).toContain('BroadcastChannel')
  })

  it('persistAuth 登录后真的调用广播', () => {
    const auth = stripComments(read('stores/auth.ts'))
    expect(block(auth, 'function persistAuth')).toContain('broadcastAuthSync(next)')
  })

  it('刷新成功与清理状态都真的调用广播', () => {
    const request = stripComments(read('api/request.ts'))
    expect(block(request, 'export async function refreshAccessToken', 1200)).toContain(
      'broadcastAuthSync(',
    )
    expect(block(request, 'function clearAuthState')).toContain('broadcastAuthSync(')
  })

  it('登出与 refreshSession 也真的调用广播', () => {
    const auth = stripComments(read('stores/auth.ts'))
    const refresh = block(auth, 'async function refreshSession', 700)
    expect(refresh).toContain('broadcastAuthSync(')
    const logout = block(auth, 'async function logout', 1200)
    expect(logout).toContain('broadcastAuthSync(')
  })
})

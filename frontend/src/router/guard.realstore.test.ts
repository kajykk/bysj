import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { resolveGuardResult } from './guard'
import { useAuthStore } from '@/stores/auth'

/**
 * ROUND_35 / M-20：用**真实 auth store** 验证「篡改角色能否进入咨询师工作台」。
 *
 * 既有 guard.test.ts 传的是手写普通对象（测试替身），只能证明纯函数逻辑；
 * 不能证明真实 store 的 isRoleVerified 计算、以及 router 是否把这个值真的
 * 传给守卫。本文件补齐这两层：
 *   1. 真实 Pinia store + 真实 JWT 解析 → isRoleVerified 由代码算出来；
 *   2. 读源码钉住 router/index.ts 的接线确实传 auth.isRoleVerified，
 *      防止「测试里传对了、运行时传的是 true」这类接线漂移。
 */

const b64 = (obj: unknown) => btoa(JSON.stringify(obj)).replace(/=+$/, '')

function jwtWithRole(role: string): string {
  return [
    b64({ alg: 'HS256', typ: 'JWT' }),
    b64({ sub: '1', role, exp: Math.floor(Date.now() / 1000) + 3600 }),
    'signature-not-verified-by-frontend',
  ].join('.')
}

describe('M-20 真实 store：未验证角色 fail-closed 到咨询师区', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    sessionStorage.clear()
  })

  it('token claim=user 但 user.role 被篡改成 counselor ⇒ /counselor/* 回登录页', () => {
    const auth = useAuthStore()
    // 真实状态：token 由后端签发（claim=user），localStorage 里的 user 被 DevTools 改过
    auth.token = jwtWithRole('user')
    auth.user = {
      id: 1,
      username: 'tampered',
      email: 't@test.com',
      role: 'counselor',
    } as never

    // 真实计算结果，不是手写布尔值
    expect(auth.isLoggedIn).toBe(true)
    expect(auth.role).toBe('counselor')
    expect(auth.isRoleVerified).toBe(false)

    const state = {
      isLoggedIn: auth.isLoggedIn,
      role: auth.role,
      roleVerified: auth.isRoleVerified,
    }
    expect(resolveGuardResult('/counselor/dashboard', { role: 'counselor' }, state)).toBe('/login')
    expect(resolveGuardResult('/counselor/reviews', { role: 'counselor' }, state)).toBe('/login')
    // 管理端同口径
    expect(resolveGuardResult('/admin/dashboard', { role: 'admin' }, state)).toBe('/login')
  })

  it('正向对照：claim 与内存角色一致时不再 fail-closed，按 meta 判 /forbidden', () => {
    const auth = useAuthStore()
    auth.token = jwtWithRole('user')
    auth.user = {
      id: 1,
      username: 'normal',
      email: 'n@test.com',
      role: 'user',
    } as never

    expect(auth.isRoleVerified).toBe(true)
    const state = {
      isLoggedIn: auth.isLoggedIn,
      role: auth.role,
      roleVerified: auth.isRoleVerified,
    }
    // 已验证但角色仍是 user ⇒ 不再是 /login，而是角色不匹配 /forbidden
    expect(resolveGuardResult('/counselor/dashboard', { role: 'counselor' }, state)).toBe('/forbidden')
    // 用户区正常放行（排除「全部拒绝」的假实现）
    expect(resolveGuardResult('/user/dashboard', { role: 'user' }, state)).toBe(true)
  })

  it('router 接线：resolveGuardResult 的 roleVerified 必须来自真实 store', () => {
    const source = readFileSync(
      resolve(__dirname, 'index.ts'),
      'utf8',
    )
    const callStart = source.indexOf('const result = resolveGuardResult(')
    expect(callStart).toBeGreaterThan(-1)
    // 只截调用块，避免命中注释或本测试自己的字符串
    const callBlock = source.slice(callStart, source.indexOf('\n  )', callStart) + 5)
    expect(callBlock).toContain('roleVerified: auth.isRoleVerified')
    // 不得把 roleVerified 硬编码成 true / 常量绕过真实 store
    expect(callBlock).not.toMatch(/roleVerified:\s*(true|false|\d)/)
  })
})

/**
 * P2-32 SSOT 闸门：防止「Blob 下载链路复制 N 份后各自漂移」复发。
 *
 * 实测背景（backend/scripts/audit_ssot_duplication.py）：
 * 旧有 **11 处**手写 Blob 下载链路（blob → createObjectURL → 建 <a> →
 * click → revokeObjectURL），分成两种 revoke 变体，其中 **4 处仍是同步
 * revoke** —— 正是 M-29 修复过的缺陷（ObjectURL 在浏览器开始下载前被
 * 回收 → 下载静默失败）在这些调用点上从未被修复。
 *
 * 本闸门把「唯一入口」变成可自动失败的检查：
 * 1. 静态：`src/` 下除 SSOT 本体外不得再出现 `document.createElement('a')`
 *    或裸 `URL.revokeObjectURL` 调用（反例闸门：新增一处即红）。
 * 2. 行为：`downloadBlob` 必须延迟 revoke、必须 append 后 remove，
 *    且 revoke 的 URL 必须与 createObjectURL 返回的一致。
 *
 * 对照实验记录（E10/E11）见 docs/CODE_REVIEW_2026-10-11.md 第八轮追记。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { downloadBlob } from '@/utils/exportUtils'

const SRC_DIR = join(process.cwd(), 'src')
const SSOT_FILE = 'src/utils/exportUtils.ts'

function* walk(dir: string): Generator<string> {
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === 'dist') continue
    const full = join(dir, entry)
    const st = statSync(full)
    if (st.isDirectory()) {
      yield* walk(full)
    } else if (/\.(ts|vue)$/.test(entry) && !/\.test\.ts$/.test(entry)) {
      yield full
    }
  }
}

// ══════════════════════════════════════════════════════════════════
// 反向闸门：静态扫描——新写一份下载链路即红
// ══════════════════════════════════════════════════════════════════

describe('P2-32 Blob 下载 SSOT 静态闸门', () => {
  const offendersAnchor: string[] = []
  const offendersRevoke: string[] = []

  for (const file of walk(SRC_DIR)) {
    const rel = relative(process.cwd(), file).replace(/\\/g, '/')
    if (rel === SSOT_FILE) continue
    const text = readFileSync(file, 'utf-8')
    const lines = text.split('\n')
    lines.forEach((line, idx) => {
      // 只认真正的调用点，跳过注释行（注释里说明 SSOT 属正常）
      const trimmed = line.trim()
      if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) return
      if (line.includes("document.createElement('a')") || line.includes('document.createElement("a")')) {
        offendersAnchor.push(`${rel}:${idx + 1}`)
      }
      // imageOptimizer 释放的是图片对象 URL，不是下载链路，登记豁免
      if (rel.includes('imageOptimizer')) return
      if (/URL\.revokeObjectURL\(/.test(line)) {
        offendersRevoke.push(`${rel}:${idx + 1}`)
      }
    })
  }

  it('src/ 下无SSOT 之外的 <a> 下载锚点（新增下载链路即红）', () => {
    expect(offendersAnchor).toEqual([])
  })

  it('src/ 下无 SSOT 之外的裸 revokeObjectURL 调用', () => {
    expect(offendersRevoke).toEqual([])
  })

  it('SSOT 本体确实持有唯一的下载锚点（防止闸门把 SSOT 一起排除掉）', () => {
    const text = readFileSync(join(process.cwd(), SSOT_FILE), 'utf-8')
    const anchorCount = (text.match(/document\.createElement\(['"]a['"]\)/g) || []).length
    expect(anchorCount).toBe(1)
  })
})

// ══════════════════════════════════════════════════════════════════
// 行为闸门：downloadBlob 的三条不变量（M-29 的修复不可退化）
// ══════════════════════════════════════════════════════════════════

describe('downloadBlob - M-29 修复不可退化', () => {
  let createObjectURLMock: ReturnType<typeof vi.fn>
  let revokeObjectURLMock: ReturnType<typeof vi.fn>
  let clickSpy: ReturnType<typeof vi.fn>
  let setTimeoutSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    createObjectURLMock = vi.fn(() => 'blob:mock-url')
    revokeObjectURLMock = vi.fn()
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: createObjectURLMock,
      revokeObjectURL: revokeObjectURLMock
    })
    clickSpy = vi.fn()
    // 捕获 click 而不是真点击
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {
      clickSpy()
    })
    setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout').mockImplementation(((fn: () => void) => {
      fn()
      return 0 as unknown as NodeJS.Timeout
    }) as unknown as typeof setTimeout)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('必须延迟 revoke 而非同步 revoke（M-29 缺陷的核心）', () => {
    const blob = new Blob(['x'], { type: 'text/plain' })
    downloadBlob(blob, 'test.txt')

    expect(createObjectURLMock).toHaveBeenCalledWith(blob)
    expect(clickSpy).toHaveBeenCalledTimes(1)
    // 同步 revoke 的 bug：click 之后 revoke 必须经由 setTimeout 延迟发生
    expect(setTimeoutSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:mock-url')
  })

  it('revoke 的 URL 必须与 createObjectURL 的返回值一致', () => {
    createObjectURLMock.mockReturnValue('blob:second-url')
    downloadBlob(new Blob(['y']), 'a.txt')
    expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:second-url')
  })

  it('必须 append 到文档后再remove（Firefox 下脱离文档的 <a>.click 可能不触发下载）', () => {
    const blob = new Blob(['z'], { type: 'text/plain' })
    let inDocAtClick = false
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      inDocAtClick = document.body.contains(this)
    })

    downloadBlob(blob, 'b.txt')

    expect(inDocAtClick).toBe(true)
    // 调用结束后不应留下残余节点
    expect(document.querySelectorAll('a[download]')).toHaveLength(0)
  })

  it('设置 download 文件名（缺失会导致浏览器用 URL 兜底成无扩展名文件名）', () => {
    let capturedName = ''
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      capturedName = this.download
    })
    downloadBlob(new Blob(['w']), 'report_2026.csv')
    expect(capturedName).toBe('report_2026.csv')
  })
})
/**
 * 设计令牌契约（UI-B1 起生效）。
 *
 * 与 styles.test.ts 的区别：那边验证「变量真的进了 document」，
 * 这里直接读 SCSS 源码验证「明暗两套是否都定义齐全」。
 * 背景：暗色块曾漏掉 --bg-page 等 7 个令牌，浅色值在暗色下原样生效，
 * 导致管理端内容区白底、边框发白。漏一个令牌，本文件必须红。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const STYLES_DIR = path.resolve(process.cwd(), 'src/styles')

function readStyle(file: string): string {
  return fs.readFileSync(path.join(STYLES_DIR, file), 'utf8')
}

/** 提取匹配选择器的大括号块，返回块内所有 `--token: value;` 声明。 */
function extractDeclarations(source: string, selector: RegExp): Array<Record<string, string>> {
  const blocks: Array<Record<string, string>> = []
  for (const match of source.matchAll(selector)) {
    const open = source.indexOf('{', match.index)
    let depth = 0
    let close = -1
    for (let i = open; i < source.length; i += 1) {
      if (source[i] === '{') depth += 1
      else if (source[i] === '}') {
        depth -= 1
        if (depth === 0) {
          close = i
          break
        }
      }
    }
    if (close === -1) throw new Error(`未闭合的选择器块: ${match[0]}`)

    // 去掉注释，避免把注释里的示例令牌当成真实声明
    const body = source.slice(open + 1, close).replace(/\/\/.*$/gm, '')
    const declarations: Record<string, string> = {}
    for (const decl of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
      declarations[decl[1]] = decl[2].trim()
    }
    blocks.push(declarations)
  }
  return blocks
}

function mergeBlocks(blocks: Array<Record<string, string>>): Record<string, string> {
  return Object.assign({}, ...blocks)
}

const variablesSource = readStyle('variables.scss')
const themeSource = readStyle('theme.scss')

// 按 main.ts 的加载顺序合并：variables.scss 在前，theme.scss 的 :root 覆盖同名令牌
const lightTokens = mergeBlocks([
  ...extractDeclarations(variablesSource, /:root\s*\{/g),
  ...extractDeclarations(themeSource, /:root\s*\{/g),
])
const darkTokens = mergeBlocks(extractDeclarations(themeSource, /html\.dark\s*\{/g))

const REQUIRED_TOKENS = [
  '--bg-page',
  '--bg-primary',
  '--bg-secondary',
  '--bg-tertiary',
  '--bg-hover',
  '--surface-1',
  '--surface-2',
  '--surface-3',
  '--card-border',
  '--text-primary',
  '--text-regular',
  '--text-secondary',
  '--text-tertiary',
  '--text-placeholder',
  '--border-color',
  '--border-light',
  '--border-lighter',
  '--border-extra-light',
  '--chart-color-primary',
  '--chart-color-success',
  '--chart-color-danger',
  '--chart-color-warning',
  '--chart-color-info',
  '--chart-color-primary-area',
  '--chart-color-primary-area-end',
  '--gradient-surface',
  '--success-light',
  '--warning-light',
  '--danger-light',
  '--info-light',
  '--shadow-base',
  '--shadow-light',
  '--shadow-card',
  '--shadow-card-hover',
  '--ring-focus',
  '--glow-primary',
  '--glow-success',
  '--glow-danger',
]

/** 这些令牌在暗色下必须给出与浅色不同的值，避免浅色值直接漏到暗色。 */
const MUST_DIVERGE = [
  '--bg-page',
  '--bg-primary',
  '--bg-secondary',
  '--bg-tertiary',
  '--bg-hover',
  '--surface-1',
  '--surface-2',
  '--surface-3',
  '--card-border',
  '--text-primary',
  '--text-regular',
  '--text-secondary',
  '--border-color',
  '--border-light',
  '--border-lighter',
  '--border-extra-light',
  '--chart-color-primary',
  '--chart-color-success',
  '--chart-color-danger',
  '--chart-color-warning',
  '--chart-color-info',
  '--gradient-surface',
  '--success-light',
  '--warning-light',
  '--danger-light',
  '--info-light',
  '--shadow-base',
  '--shadow-light',
  '--shadow-card',
  '--shadow-card-hover',
  '--ring-focus',
  '--glow-primary',
  '--glow-success',
  '--glow-danger',
]

type Rgb = [number, number, number]

function parseHex(value: string): Rgb {
  const hex = value.trim()
  if (!/^#[0-9a-f]{6}$/i.test(hex)) {
    throw new Error(`契约测试只支持 6 位 hex，收到: ${hex}`)
  }
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ]
}

function relativeLuminance(rgb: Rgb): number {
  const [r, g, b] = rgb.map((channel) => {
    const c = channel / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrastRatio(foreground: string, background: string): number {
  const lighter = Math.max(
    relativeLuminance(parseHex(foreground)),
    relativeLuminance(parseHex(background)),
  )
  const darker = Math.min(
    relativeLuminance(parseHex(foreground)),
    relativeLuminance(parseHex(background)),
  )
  return (lighter + 0.05) / (darker + 0.05)
}

describe('设计令牌契约：暗色必须覆盖', () => {
  for (const token of REQUIRED_TOKENS) {
    it(`${token} 在明暗两套中都有定义`, () => {
      expect(lightTokens[token], `浅色缺少 ${token}`).toBeTruthy()
      expect(darkTokens[token], `暗色缺少 ${token}`).toBeTruthy()
    })
  }
})

describe('设计令牌契约：暗色不得复用浅色值', () => {
  for (const token of MUST_DIVERGE) {
    it(`${token} 暗色值与浅色值不同`, () => {
      expect(darkTokens[token]).not.toBe(lightTokens[token])
    })
  }
})

describe('设计令牌契约：表面层级与对比度', () => {
  it('卡片面（surface-1）在两套主题下都比页面底色（bg-page）更亮', () => {
    expect(relativeLuminance(parseHex(lightTokens['--surface-1']))).toBeGreaterThan(
      relativeLuminance(parseHex(lightTokens['--bg-page'])),
    )
    expect(relativeLuminance(parseHex(darkTokens['--surface-1']))).toBeGreaterThan(
      relativeLuminance(parseHex(darkTokens['--bg-page'])),
    )
  })

  it('暗色表面层级逐级提亮：surface-1 < surface-2 < surface-3', () => {
    const [s1, s2, s3] = ['--surface-1', '--surface-2', '--surface-3'].map((token) =>
      relativeLuminance(parseHex(darkTokens[token])),
    )
    expect(s2).toBeGreaterThan(s1)
    expect(s3).toBeGreaterThan(s2)
  })

  it.each([
    ['light', lightTokens],
    ['dark', darkTokens],
  ])('%s 主题正文对比度满足 WCAG AA（≥4.5:1）', (_name, tokens) => {
    expect(contrastRatio(tokens['--text-primary'], tokens['--surface-1'])).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(tokens['--text-regular'], tokens['--surface-1'])).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(tokens['--text-secondary'], tokens['--surface-1'])).toBeGreaterThanOrEqual(4.5)
  })

  it.each([
    ['light', lightTokens],
    ['dark', darkTokens],
  ])('%s 主题图表色对背景满足非文本 3:1', (_name, tokens) => {
    for (const token of [
      '--chart-color-primary',
      '--chart-color-success',
      '--chart-color-warning',
      '--chart-color-danger',
      '--chart-color-info',
    ]) {
      expect(
        contrastRatio(tokens[token], tokens['--surface-1']),
        `${token} 对比度不足`,
      ).toBeGreaterThanOrEqual(3)
    }
  })
})

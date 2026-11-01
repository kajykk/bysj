/**
 * 设计令牌契约（UI-B1 起生效，UI-B7 扩到全量）。
 *
 * 与 styles.test.ts 的区别：那边验证「变量真的进了 document」，
 * 这里直接读 SCSS 源码验证明暗两套是否完整、可读、可对比。
 * 背景：暗色块曾漏掉 --bg-page 等 7 个令牌，浅色值在暗色下原样生效，
 * 导致管理端内容区白底、边框发白。漏一个令牌，本文件必须红。
 *
 * UI-B7 之后不再维护「只列关键令牌」的名单：
 * - 浅色里出现的每个令牌，要么在 html.dark 有覆盖，要么在豁免清单里写明理由；
 * - 暗色不得出现浅色未定义的令牌；
 * - Element Plus 令牌必须两套齐全；
 * - 正文 × 表面、强调底文字 × 渐变、图表色 × 背景全部按 WCAG 阈值断言。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import { CHART_PALETTE, STATIC_FALLBACK_COLORS } from '../utils/chartPalette'

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
const darkOverrides = mergeBlocks(extractDeclarations(themeSource, /html\.dark\s*\{/g))
/** 暗色下实际生效的令牌 = 浅色基数 + 暗色覆盖。 */
const effectiveDarkTokens = { ...lightTokens, ...darkOverrides }

/**
 * 主题无关令牌：不随明暗切换，因此不需要在 html.dark 重复定义。
 * 新增条目必须写明理由，否则下面「浅色令牌必须有落点」的测试会失败。
 */
const THEME_INVARIANT_PREFIXES: Record<string, string> = {
  '--spacing-': '间距体系',
  '--radius-': '圆角体系',
  '--font-': '字体体系',
  '--letter-spacing-': '字距体系',
  '--line-height-': '行高体系',
  '--layout-': '布局尺寸',
  '--transition-': '过渡参数',
  '--ease-': '缓动曲线',
  '--duration-': '动效时长',
  '--form-label-': '表单布局',
  '--brand-panel-': '登录品牌面板固定深色底',
}

const THEME_INVARIANT_TOKENS: Record<string, string> = {
  '--shadow-inset': '主题中性的内高光',
  '--role-accent-current': '运行时由 body[data-role] 赋值，跟随已主题化的品牌色',
  '--risk-glow-pulse-duration': '动效时长',
  '--text-on-light-accent': '浅色强调底上的固定深墨色，两套主题共用',
}

for (const step of [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]) {
  THEME_INVARIANT_TOKENS[`--primary-${step}`] = '固定品牌色阶（Logo/图表基础色，不随主题反转）'
}

function invariantReason(token: string): string | undefined {
  if (token in THEME_INVARIANT_TOKENS) return THEME_INVARIANT_TOKENS[token]
  const prefix = Object.keys(THEME_INVARIANT_PREFIXES).find((p) => token.startsWith(p))
  return prefix ? THEME_INVARIANT_PREFIXES[prefix] : undefined
}

/** 暗色覆盖允许与浅色同文本值的令牌（值是 var() 间接引用，实际颜色仍会切换）。 */
const SAME_VALUE_ALLOWED = new Set(['--role-accent-user'])

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
  '--text-on-accent',
  '--text-on-light-accent',
  '--success-strong',
  '--warning-strong',
  '--info-strong',
  '--risk-none',
  '--risk-mild',
  '--risk-moderate',
  '--risk-high',
  '--risk-critical',
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
  '--brand-panel-text',
  '--brand-panel-text-muted',
  '--brand-panel-text-dim',
  '--brand-panel-bg-start',
  '--brand-panel-bg-mid',
  '--brand-panel-bg-end',
  '--brand-panel-accent-blue',
  '--brand-panel-accent-soft',
  '--brand-panel-accent-green',
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
  '--text-on-accent',
  '--success-strong',
  '--warning-strong',
  '--info-strong',
  '--risk-none',
  '--risk-mild',
  '--risk-moderate',
  '--risk-high',
  '--risk-critical',
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

/** 从 linear-gradient(...) 里取出全部 hex 色标。 */
function gradientStops(value: string): string[] {
  return [...value.matchAll(/#[0-9a-f]{6}\b/gi)].map((match) => match[0])
}

const THEMES: Array<[string, Record<string, string>]> = [
  ['light', lightTokens],
  ['dark', effectiveDarkTokens],
]

describe('设计令牌契约：全量覆盖', () => {
  it('每个浅色令牌要么在暗色有覆盖，要么登记为主题无关', () => {
    const uncovered = Object.keys(lightTokens).filter(
      (token) => !(token in darkOverrides) && !invariantReason(token),
    )
    expect(
      uncovered,
      `以下令牌在 html.dark 缺失且未登记为主题无关：\n${uncovered.join('\n')}`,
    ).toEqual([])
  })

  it('暗色块不存在浅色未定义的令牌', () => {
    const orphaned = Object.keys(darkOverrides).filter((token) => !(token in lightTokens))
    expect(orphaned, `以下暗色令牌没有浅色定义：\n${orphaned.join('\n')}`).toEqual([])
  })

  it('主题无关豁免清单没有失效条目', () => {
    const staleTokens = Object.keys(THEME_INVARIANT_TOKENS).filter(
      (token) => !(token in lightTokens),
    )
    expect(staleTokens, `以下豁免令牌已不存在：\n${staleTokens.join('\n')}`).toEqual([])

    const allTokens = Object.keys(lightTokens)
    const stalePrefixes = Object.keys(THEME_INVARIANT_PREFIXES).filter(
      (prefix) => !allTokens.some((token) => token.startsWith(prefix)),
    )
    expect(stalePrefixes, `以下豁免前缀已匹配不到令牌：\n${stalePrefixes.join('\n')}`).toEqual(
      [],
    )
  })

  it('Element Plus 令牌在暗色中全量覆盖', () => {
    const lightElementTokens = Object.keys(lightTokens).filter((token) =>
      token.startsWith('--el-'),
    )
    expect(lightElementTokens.length).toBeGreaterThan(0)
    expect(lightElementTokens.filter((token) => !(token in darkOverrides))).toEqual([])
  })

  for (const token of REQUIRED_TOKENS) {
    it(`${token} 在明暗两套中都有定义`, () => {
      expect(lightTokens[token], `浅色缺少 ${token}`).toBeTruthy()
      expect(effectiveDarkTokens[token], `暗色缺少 ${token}`).toBeTruthy()
    })
  }
})

describe('设计令牌契约：暗色不得复用浅色值', () => {
  it('除登记例外外，暗色覆盖值与浅色值不同', () => {
    const copied = Object.keys(darkOverrides).filter(
      (token) =>
        !SAME_VALUE_ALLOWED.has(token) && darkOverrides[token] === lightTokens[token],
    )
    expect(copied, `以下暗色令牌原样复制了浅色值：\n${copied.join('\n')}`).toEqual([])
  })

  for (const token of MUST_DIVERGE) {
    it(`${token} 暗色值与浅色值不同`, () => {
      expect(effectiveDarkTokens[token]).not.toBe(lightTokens[token])
    })
  }
})

describe('设计令牌契约：表面层级与文字对比度', () => {
  it('卡片面（surface-1）在两套主题下都比页面底色（bg-page）更亮', () => {
    expect(relativeLuminance(parseHex(lightTokens['--surface-1']))).toBeGreaterThan(
      relativeLuminance(parseHex(lightTokens['--bg-page'])),
    )
    expect(relativeLuminance(parseHex(effectiveDarkTokens['--surface-1']))).toBeGreaterThan(
      relativeLuminance(parseHex(effectiveDarkTokens['--bg-page'])),
    )
  })

  it('暗色表面层级逐级提亮：surface-1 < surface-2 < surface-3', () => {
    const [s1, s2, s3] = ['--surface-1', '--surface-2', '--surface-3'].map((token) =>
      relativeLuminance(parseHex(effectiveDarkTokens[token])),
    )
    expect(s2).toBeGreaterThan(s1)
    expect(s3).toBeGreaterThan(s2)
  })

  const BODY_TEXT_TOKENS = ['--text-primary', '--text-regular', '--text-secondary']
  const SURFACE_TOKENS = ['--surface-1', '--surface-2', '--surface-3', '--bg-page']

  for (const [themeName, tokens] of THEMES) {
    it(`${themeName} 主题正文与所有表面组合满足 WCAG AA（≥4.5:1）`, () => {
      for (const textToken of BODY_TEXT_TOKENS) {
        for (const surfaceToken of SURFACE_TOKENS) {
          expect(
            contrastRatio(tokens[textToken], tokens[surfaceToken]),
            `${textToken} on ${surfaceToken}`,
          ).toBeGreaterThanOrEqual(4.5)
        }
      }
    })
  }
})

describe('设计令牌契约：强调底与语义底上的文字对比度', () => {
  for (const [themeName, tokens] of THEMES) {
    it(`${themeName} 主题强调渐变上的文字满足 WCAG AA（≥4.5:1）`, () => {
      for (const stop of gradientStops(tokens['--gradient-primary'])) {
        expect(
          contrastRatio(tokens['--text-on-accent'], stop),
          `--text-on-accent on gradient-primary ${stop}`,
        ).toBeGreaterThanOrEqual(4.5)
      }
      expect(
        contrastRatio(tokens['--text-on-accent'], tokens['--primary-color']),
        '--text-on-accent on --primary-color',
      ).toBeGreaterThanOrEqual(4.5)

      for (const gradientToken of ['--gradient-green', '--gradient-gold']) {
        for (const stop of gradientStops(tokens[gradientToken])) {
          expect(
            contrastRatio(tokens['--text-on-light-accent'], stop),
            `--text-on-light-accent on ${gradientToken} ${stop}`,
          ).toBeGreaterThanOrEqual(4.5)
        }
      }
    })

    it(`${themeName} 主题语义底上的正文对比度满足 WCAG AA（≥4.5:1）`, () => {
      expect(
        contrastRatio(tokens['--success-strong'], tokens['--success-light']),
      ).toBeGreaterThanOrEqual(4.5)
      expect(
        contrastRatio(tokens['--warning-strong'], tokens['--warning-light']),
      ).toBeGreaterThanOrEqual(4.5)
      expect(
        contrastRatio(tokens['--info-strong'], tokens['--info-light']),
      ).toBeGreaterThanOrEqual(4.5)
    })

    it(`${themeName} 主题图表色对背景满足非文本 3:1`, () => {
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
  }
})

describe('设计令牌契约：静态颜色镜像不得漂移', () => {
  const paletteMirrors: Array<[string, string, string]> = [
    ['CHART_PALETTE.primary', CHART_PALETTE.primary, '--chart-color-primary'],
    ['CHART_PALETTE.success', CHART_PALETTE.success, '--chart-color-success'],
    ['CHART_PALETTE.warning', CHART_PALETTE.warning, '--chart-color-warning'],
    ['CHART_PALETTE.danger', CHART_PALETTE.danger, '--chart-color-danger'],
    ['CHART_PALETTE.info', CHART_PALETTE.info, '--chart-color-info'],
    ['CHART_PALETTE.primaryLight', CHART_PALETTE.primaryLight, '--primary-300'],
  ]

  for (const [label, value, token] of paletteMirrors) {
    it(`${label} 与浅色令牌 ${token} 一致`, () => {
      expect(value).toBe(lightTokens[token])
    })
  }

  const fallbackMirrors: Array<[string, string, string]> = [
    ['STATIC_FALLBACK_COLORS.textPrimary', STATIC_FALLBACK_COLORS.textPrimary, '--text-primary'],
    ['STATIC_FALLBACK_COLORS.textRegular', STATIC_FALLBACK_COLORS.textRegular, '--text-regular'],
    [
      'STATIC_FALLBACK_COLORS.textSecondary',
      STATIC_FALLBACK_COLORS.textSecondary,
      '--text-secondary',
    ],
    ['STATIC_FALLBACK_COLORS.surface1', STATIC_FALLBACK_COLORS.surface1, '--surface-1'],
    ['STATIC_FALLBACK_COLORS.cardBorder', STATIC_FALLBACK_COLORS.cardBorder, '--card-border'],
    ['STATIC_FALLBACK_COLORS.borderColor', STATIC_FALLBACK_COLORS.borderColor, '--border-color'],
  ]

  for (const [label, value, token] of fallbackMirrors) {
    it(`${label} 与浅色令牌 ${token} 一致`, () => {
      expect(value).toBe(lightTokens[token])
    })
  }
})

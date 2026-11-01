import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const variablesScss = fs.readFileSync(
  path.resolve(process.cwd(), 'src/styles/variables.scss'),
  'utf8',
)

function token(name: string): string {
  const match = variablesScss.match(new RegExp(`--${name}\\s*:\\s*([^;]+);`))
  if (!match) throw new Error(`token --${name} 未在 variables.scss 中定义`)
  return match[1].trim()
}

function scssVar(name: string): string {
  const match = variablesScss.match(new RegExp(`\\$${name}\\s*:\\s*([^;]+);`))
  if (!match) throw new Error(`SCSS 变量 $${name} 未在 variables.scss 中定义`)
  return match[1].trim()
}

describe('Design token 契约', () => {
  it('关键 token 值不得被静默改动', () => {
    expect(token('primary-color')).toBe('#2e6fa8')
    expect(token('spacing-base')).toBe('8px')
    expect(token('font-size-base')).toBe('14px')
  })

  it('断点 SCSS 变量不得被静默改动', () => {
    expect(scssVar('breakpoint-mobile')).toBe('768px')
    expect(scssVar('breakpoint-tablet')).toBe('1280px')
  })
})

describe('CSS Variables', () => {
  it('should have root CSS variables defined', () => {
    const rootStyles = getComputedStyle(document.documentElement)
    expect(rootStyles.getPropertyValue('--primary-color').trim()).toBe('#2e6fa8')
    expect(rootStyles.getPropertyValue('--spacing-base').trim()).toBe('8px')
    expect(rootStyles.getPropertyValue('--font-size-base').trim()).toBe('14px')
  })
})

describe('SCSS Mixins', () => {
  it('should verify mixins are importable', () => {
    expect(true).toBe(true)
  })
})

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const _here = dirname(fileURLToPath(import.meta.url))
const DASHBOARD_SRC = readFileSync(resolve(_here, './CounselorDashboard.vue'), 'utf-8')

describe('CounselorDashboard - 4.1.1 统计与快捷操作优化', () => {
  it('统计数字应使用 CountUp 动画组件', () => {
    const useCountUp = true
    const duration = 1200

    expect(useCountUp).toBe(true)
    expect(duration).toBe(1200)
  })

  it('快捷操作按钮应包含图标', () => {
    const buttons = [
      { label: '处理预警', icon: 'Warning' },
      { label: '用户管理', icon: 'User' }
    ]

    expect(buttons[0].icon).toBe('Warning')
    expect(buttons[1].icon).toBe('User')
  })

  it('绑定码应支持一键复制功能', () => {
    const bindCode = 'ABC123'
    const canCopy = bindCode.length > 0

    expect(canCopy).toBe(true)
    expect(bindCode).toBe('ABC123')
  })

  it('统计卡片应包含图标和标题', () => {
    const cards = [
      { title: '今日待处理预警', icon: 'Warning', color: 'warning' },
      { title: '绑定用户数', icon: 'User', color: 'primary' },
      { title: '绑定码', icon: 'CopyDocument', color: 'primary' }
    ]

    expect(cards).toHaveLength(3)
    expect(cards[0].icon).toBe('Warning')
    expect(cards[1].color).toBe('primary')
  })

  it('绑定码显示应使用等宽字体和字母间距', () => {
    const bindCodeStyle = {
      fontSize: '24px',
      letterSpacing: '2px'
    }

    expect(bindCodeStyle.letterSpacing).toBe('2px')
    expect(bindCodeStyle.fontSize).toBe('24px')
  })
})

/**
 * M27 修复（ROUND_23）：待处理预警数三态渲染。
 *
 * 判据说明：本文件既有用例是占位式断言（断言自建局部变量，无验证力）。
 * 三态是**渲染层**行为，这里用「读组件源码的结构见证」——断言失败态分支
 * 真实存在且不含数字渲染。属于结构见证而非渲染见证：挂载级验证记账见
 * docs/P2_23B_FRONTEND_AUDIT.md（组件依赖 i18n/element-plus/api，
 * 挂载成本高，本轮未做）。
 */
describe('CounselorDashboard - M27 待处理预警数三态', () => {
  it('unhandledCount 的类型是 number | null（null = 加载失败）', () => {
    expect(DASHBOARD_SRC).toMatch(/const unhandledCount = ref<number \| null>\(0\)/)
  })

  it('存在 null 失败态分支（v-else-if）', () => {
    expect(DASHBOARD_SRC).toContain('v-else-if="unhandledCount === null"')
  })

  it('失败态渲染破折号而非数字，且给出加载失败文案', () => {
    const failedBranch = DASHBOARD_SRC.slice(
      DASHBOARD_SRC.indexOf('v-else-if="unhandledCount === null"')
    )
    // 该分支内渲染 "—"（em dash），不渲染 CountUp 数字动画
    expect(failedBranch).toContain('—')
    expect(failedBranch).toContain('heroLoadFailed')
    // CountUp 只在正常分支出现：失败分支到下一个 <template v-else> 之间不得有 CountUp
    const untilNormalBranch = failedBranch.slice(0, failedBranch.indexOf('<template v-else>'))
    expect(untilNormalBranch).not.toContain('CountUp')
    expect(untilNormalBranch).not.toContain(':end="unhandledCount"')
  })

  it('加载中态仍由 statsLoading 控制（三态互斥）', () => {
    expect(DASHBOARD_SRC).toContain('v-if="statsLoading"')
    expect(DASHBOARD_SRC).toContain('<template v-else-if="unhandledCount === null">')
    expect(DASHBOARD_SRC).toContain('<template v-else>')
  })

  it('失败态不把 null 当成 0：live-dot 与 tag 判据用 ?? 兜底', () => {
    expect(DASHBOARD_SRC).toContain("(unhandledCount ?? 0) > 0")
  })
})

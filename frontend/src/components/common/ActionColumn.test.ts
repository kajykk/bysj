/**
 * ActionColumn 禁用语义回归测试（FIX-2026-10-08）。
 *
 * 缺陷: 模板用 `v-if="disabledReason"` 决定走「禁用+tooltip」分支，且 handleClick
 *       里有 `if (... || props.disabledReason) return` —— 于是**只要调用方传了
 *       disabledReason，按钮就永远不可点**，与 `disabled` prop 完全无关。
 *
 * 实锤: UserAssessmentsPage.vue:113 无条件传入 `t('userAssessments.noPermission')`
 *       （恒为 '无权限'），实测操作列按钮 class 带 `is-disabled`、点击后 router.push
 *       **0 次** —— 用户看得见「查看详情」，却永远点不动。
 *
 *       全仓 12 处调用点**全部同时传了 `:disabled` 与 `:disabled-reason`**，其中
 *       4 处是无条件恒传（AdminAuditLogsPage:204 / AdminOperationLogsPage:151 /
 *       CounselorUsersPage:114 / UserAssessmentsPage:113），另外 8 处在条件为真时
 *       传 i18n 文案、为假时传 undefined，行为正确 —— 说明组件把「禁用原因」
 *       当成「禁用条件」用，是组件自身的语义缺陷，不该让每个调用方各自绕过。
 *
 * 正确语义: `disabled` 决定按钮是否禁用；`disabledReason` 只是**禁用时才显示**
 *       的原因提示。二者解耦后 12 处调用点无需改动即可全部正确。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ActionColumn from './ActionColumn.vue'

function mountAction(props: Record<string, unknown> = {}) {
  return mount(ActionColumn, {
    props: { label: '查看详情', ...props },
  })
}

/** tooltip 分支下按钮被 span.action-wrap 包着，统一按 tag 找真正可点的那个。 */
async function clickButton(wrapper: ReturnType<typeof mountAction>) {
  await wrapper.find('button').trigger('click')
}

describe('ActionColumn 禁用语义（disabled 与 disabledReason 解耦）', () => {
  it('有权限时按钮可点击并派发 action（改前被恒传的 reason 卡死）', async () => {
    const wrapper = mountAction({ disabled: false, disabledReason: '无权限', confirmText: '' })
    const button = wrapper.find('button')

    expect(button.classes()).not.toContain('is-disabled')
    await clickButton(wrapper)
    expect(wrapper.emitted('action')).toHaveLength(1)
  })

  it('disabled 为 true 时按钮禁用且不派发', async () => {
    const wrapper = mountAction({ disabled: true, disabledReason: '无权限' })
    const button = wrapper.find('button')

    expect(button.classes()).toContain('is-disabled')
    await clickButton(wrapper)
    expect(wrapper.emitted('action')).toBeUndefined()
  })

  it('disabled 为 true 但没有 reason 时仍然禁用（禁用只看 disabled）', async () => {
    const wrapper = mountAction({ disabled: true })
    expect(wrapper.find('button').classes()).toContain('is-disabled')
  })

  it('loading 时不派发多次', async () => {
    const wrapper = mountAction({ loading: true })
    await clickButton(wrapper)
    expect(wrapper.emitted('action')).toBeUndefined()
  })
})

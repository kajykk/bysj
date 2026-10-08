<!--
  FIX-2026-10-08：原写法 `v-if="disabledReason"` 把「禁用原因」当成「禁用条件」用了
  —— 只要调用方传了 reason，按钮就永久不可点，与 disabled prop 无关。
  实锤：UserAssessmentsPage 的「查看详情」实测带 is-disabled、点击后 router.push 0 次。
  改为 `disabled && disabledReason`：禁用与否只看 disabled，reason 只是禁用时的提示。
-->
<template>
  <div class="action-column">
    <el-tooltip
      v-if="disabled && disabledReason"
      :content="disabledReason"
      placement="top"
    >
      <span class="action-wrap">
        <el-button
          :link="link"
          :type="type"
          :disabled="true"
          :loading="loading"
          size="small"
        >
          {{ label }}
        </el-button>
      </span>
    </el-tooltip>

    <el-button
      v-else
      :link="link"
      :type="type"
      :disabled="disabled"
      :loading="loading"
      size="small"
      @click="handleClick"
    >
      {{ label }}
    </el-button>

    <el-tag
      v-if="showAudit"
      size="small"
      type="info"
      effect="plain"
    >
      审计动作
    </el-tag>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus'
// ISS-095 TODO：操作按钮在小屏可考虑统一收敛到 el-dropdown 菜单中，避免列宽被按钮挤压
// ISS-091 TODO：confirmText/confirmTitle 目前依赖父组件传入，可补充默认值兜底以保证文案一致性

const props = withDefaults(
  defineProps<{
    label: string
    type?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
    loading?: boolean
    disabled?: boolean
    disabledReason?: string
    confirmText?: string
    confirmTitle?: string
    link?: boolean
    showAudit?: boolean
  }>(),
  {
    type: 'primary',
    loading: false,
    disabled: false,
    link: true,
    showAudit: false,
    confirmTitle: '确认操作',
    disabledReason: '',
    confirmText: '确定'
  }
)

const emit = defineEmits<{
  action: []
}>()

const handleClick = async () => {
  // FIX-2026-10-08：原判断里的 `|| props.disabledReason` 会让「传了原因文案」变成
  // 「不可点击」。权限判断应只由 disabled 表达，文案不参与行为决策。
  if (props.disabled || props.loading) return

  if (props.confirmText) {
    try {
      await ElMessageBox.confirm(props.confirmText, props.confirmTitle, { type: 'warning' })
    } catch {
      return
    }
  }

  emit('action')
}
</script>

<style scoped>
.action-column {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.action-wrap {
  display: inline-flex;
}
</style>

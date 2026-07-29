<template>
  <div
    class="empty-state"
    role="status"
    aria-live="polite"
  >
    <div class="empty-image">
      <!-- UI 升级 v3.2: 优先使用插画插槽,其次按 variant 选内置插画,最后回退到图标 -->
      <slot name="image">
        <component
          :is="illustrationComponent"
          v-if="illustrationComponent"
        />
        <el-icon
          v-else
          :size="imageSize"
          :color="resolvedImageColor"
          aria-hidden="true"
        >
          <Document />
        </el-icon>
      </slot>
    </div>
    <div
      class="empty-title"
      role="heading"
      aria-level="2"
    >
      {{ title }}
    </div>
    <div
      v-if="description"
      class="empty-description"
    >
      {{ description }}
    </div>
    <div
      v-if="$slots.action || showAction"
      class="empty-action"
    >
      <slot name="action">
        <el-button
          type="primary"
          @click="handleAction"
        >
          {{ resolvedActionText }}
        </el-button>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
// UI 升级 v3.2: 场景化插画组件
import EmptyAssessment from './illustrations/EmptyAssessment.vue'
import EmptyWarning from './illustrations/EmptyWarning.vue'
import EmptyReport from './illustrations/EmptyReport.vue'
import EmptyUser from './illustrations/EmptyUser.vue'

type EmptyVariant = 'assessment' | 'warning' | 'report' | 'user' | 'default'

interface Props {
  title: string
  description?: string
  imageSize?: number
  imageColor?: string
  showAction?: boolean
  actionText?: string
  /** UI 升级 v3.2: 场景化插画变体,自动选择对应 SVG 插画 */
  variant?: EmptyVariant
}

// ISS-029 修复：硬编码颜色与中文迁移到设计系统/i18n
const props = withDefaults(defineProps<Props>(), {
  description: '',
  imageSize: 60,
  imageColor: '',
  showAction: false,
  actionText: '',
  variant: 'default',
})

const emit = defineEmits<{
  action: []
}>()

const { t } = useI18n()

// 默认使用设计系统令牌（--text-placeholder），允许调用方覆盖
const resolvedImageColor = computed(() => {
  return props.imageColor || 'var(--text-placeholder, #dcdfe6)'
})

// UI 升级 v3.2: 按 variant 选择对应插画组件
const ILLUSTRATION_MAP: Record<EmptyVariant, Component | null> = {
  assessment: EmptyAssessment,
  warning: EmptyWarning,
  report: EmptyReport,
  user: EmptyUser,
  default: null,  // default 回退到原来的 Document 图标
}

const illustrationComponent = computed(() => ILLUSTRATION_MAP[props.variant])

// 默认操作文本走 i18n（common.create），允许调用方覆盖
const resolvedActionText = computed(() => {
  return props.actionText || t('common.create')
})

const handleAction = () => {
  emit('action')
}
</script>

<style scoped>
/* ISS-029 修复：使用设计系统令牌 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px var(--spacing-xl);
  text-align: center;
}

.empty-image {
  margin-bottom: var(--spacing-lg);
}

/* UI 升级 v3.2: 插画容器 - 居中显示,继承 currentColor */
.empty-image :deep(.empty-illustration) {
  width: 80px;
  height: 80px;
}

.empty-title {
  font-size: var(--font-size-base);
  color: var(--text-regular);
  margin-bottom: var(--spacing-sm);
  font-weight: var(--font-weight-medium);
}

.empty-description {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-lg);
  max-width: 300px;
  line-height: var(--line-height-normal);
}

.empty-action {
  margin-top: var(--spacing-sm);
}

/* 减少动效偏好:关闭插画浮动 */
@media (prefers-reduced-motion: reduce) {
  .empty-image :deep(.empty-illustration) {
    animation: none !important;
  }
}
</style>

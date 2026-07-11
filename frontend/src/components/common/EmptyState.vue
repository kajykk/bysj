<template>
  <div
    class="empty-state"
    role="status"
    aria-live="polite"
  >
    <div class="empty-image">
      <slot name="image">
        <el-icon
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
import { computed } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

interface Props {
  title: string
  description?: string
  imageSize?: number
  imageColor?: string
  showAction?: boolean
  actionText?: string
}

// ISS-029 修复：硬编码颜色与中文迁移到设计系统/i18n
const props = withDefaults(defineProps<Props>(), {
  description: '',
  imageSize: 60,
  imageColor: '',
  showAction: false,
  actionText: '',
})

const emit = defineEmits<{
  action: []
}>()

const { t } = useI18n()

// 默认使用设计系统令牌（--text-placeholder），允许调用方覆盖
const resolvedImageColor = computed(() => {
  return props.imageColor || 'var(--text-placeholder, #dcdfe6)'
})

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
</style>

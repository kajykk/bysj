<template>
  <div>
    <div
      v-if="loading"
      class="state-wrap"
    >
      <el-skeleton
        :rows="skeletonRows"
        animated
      />
    </div>
    <div
      v-else-if="errorMessage"
      class="state-wrap state-error"
    >
      <el-result
        icon="error"
        :title="t('common.loadFailed')"
        :sub-title="errorMessage"
      >
        <template #extra>
          <el-button
            type="primary"
            @click="handleRetry"
          >
            {{ t('common.retry') }}
          </el-button>
        </template>
      </el-result>
      <div
        v-if="errorCode"
        class="error-code"
      >
        {{ t('common.errorCode', { code: errorCode }) }}
      </div>
    </div>
    <div
      v-else-if="empty"
      class="state-wrap state-empty"
    >
      <el-empty :description="emptyText || t('common.noData')">
        <template #image>
          <slot name="empty-image">
            <el-icon
              :size="60"
              color="var(--text-placeholder, #dcdfe6)"
            >
              <Document />
            </el-icon>
          </slot>
        </template>
        <template #description>
          <div class="empty-description">
            <div class="empty-title">
              {{ emptyTitle || t('common.noData') }}
            </div>
            <div
              v-if="emptyDescription"
              class="empty-subtitle"
            >
              {{ emptyDescription }}
            </div>
          </div>
        </template>
        <template #default>
          <slot name="empty-action">
            <el-button
              v-if="showEmptyAction"
              type="primary"
              @click="handleEmptyAction"
            >
              {{ emptyActionText }}
            </el-button>
          </slot>
        </template>
      </el-empty>
    </div>
    <slot v-else />
  </div>
</template>

<script setup lang="ts">
import { Document } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
// ISS-096 TODO：错误/空状态渲染后建议自动聚焦错误容器或重试按钮，方便键盘用户快速操作

interface Props {
  loading: boolean
  empty: boolean
  emptyText?: string
  emptyTitle?: string
  emptyDescription?: string
  showEmptyAction?: boolean
  emptyActionText?: string
  errorMessage?: string
  errorCode?: string
  skeletonRows?: number
}

// ISS-029 修复：硬编码中文迁移到 i18n，使用 common.* 通用键
withDefaults(defineProps<Props>(), {
  emptyText: '',
  emptyTitle: '',
  emptyDescription: '',
  showEmptyAction: false,
  emptyActionText: '',
  errorMessage: '',
  errorCode: '',
  skeletonRows: 4,
})

const emit = defineEmits<{
  retry: []
  emptyAction: []
}>()

const { t } = useI18n()

const handleRetry = () => {
  emit('retry')
}

const handleEmptyAction = () => {
  emit('emptyAction')
}
</script>

<style scoped>
/* ISS-029 修复：使用设计系统令牌 */
.state-wrap {
  padding: var(--spacing-sm) 0;
}

.state-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.error-code {
  margin-top: var(--spacing-sm);
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  font-family: var(--font-family-mono);
}

.state-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.empty-description {
  text-align: center;
  margin-top: var(--spacing-lg);
}

.empty-title {
  font-size: var(--font-size-base);
  color: var(--text-regular);
  margin-bottom: var(--spacing-sm);
}

.empty-subtitle {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
</style>

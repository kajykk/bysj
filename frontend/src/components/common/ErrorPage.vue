<template>
  <div class="error-page">
    <div class="error-content">
      <!-- 错误图标 -->
      <div class="error-icon">
        <svg
          v-if="code === '404'"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <circle
            cx="12"
            cy="12"
            r="10"
          />
          <path d="M8 8l8 8M16 8l-8 8" />
        </svg>
        <svg
          v-else-if="code === '403'"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <rect
            x="3"
            y="11"
            width="18"
            height="11"
            rx="2"
            ry="2"
          />
          <path d="M7 11V7a5 5 0 0110 0v4" />
        </svg>
        <svg
          v-else-if="code === '500'"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <polygon points="12 2 2 7 12 12 22 7 12 2" />
          <polyline points="2 17 12 22 22 17" />
          <polyline points="2 12 12 17 22 12" />
        </svg>
        <svg
          v-else
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <circle
            cx="12"
            cy="12"
            r="10"
          />
          <line
            x1="12"
            y1="8"
            x2="12"
            y2="12"
          />
          <line
            x1="12"
            y1="16"
            x2="12.01"
            y2="16"
          />
        </svg>
      </div>

      <!-- 错误代码 -->
      <h1 class="error-code">
        {{ code }}
      </h1>

      <!-- 错误标题 -->
      <h2 class="error-title">
        {{ title }}
      </h2>

      <!-- 错误描述 -->
      <p class="error-description">
        {{ description }}
      </p>

      <!-- 操作按钮 -->
      <div class="error-actions">
        <el-button
          type="primary"
          @click="goHome"
        >
          {{ t('error.goHome') }}
        </el-button>
        <el-button
          v-if="showBack"
          @click="goBack"
        >
          {{ t('error.goBack') }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

interface Props {
  code?: string
  title?: string
  description?: string
  showBack?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  code: '404',
  showBack: true,
  title: '',
  description: '',
})

const router = useRouter()
const { t } = useI18n()

// ISS-027 修复：硬编码中文迁移到 i18n，通过 code 映射到对应文案
const defaultTitleKey = computed(() => {
  switch (props.code) {
    case '404': return 'error.page404Title'
    case '403': return 'error.page403Title'
    case '500': return 'error.page500Title'
    default: return 'error.unknownTitle'
  }
})

const defaultDescriptionKey = computed(() => {
  switch (props.code) {
    case '404': return 'error.page404Description'
    case '403': return 'error.page403Description'
    case '500': return 'error.page500Description'
    default: return 'error.unknownDescription'
  }
})

const title = computed(() => {
  if (props.title) return props.title
  return t(defaultTitleKey.value)
})

const description = computed(() => {
  if (props.description) return props.description
  return t(defaultDescriptionKey.value)
})

const goHome = () => {
  router.push('/')
}

const goBack = () => {
  router.back()
}
</script>

<style scoped>
/* ISS-027/036 修复：改用 CSS 变量，自动支持深色模式（变量在 theme.scss 中按 html.dark 重写） */
.error-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: var(--spacing-xl);
  background: linear-gradient(135deg, var(--bg-page) 0%, var(--bg-tertiary, #e4e7ed) 100%);
}

.error-content {
  text-align: center;
  max-width: 480px;
}

.error-icon {
  width: 120px;
  height: 120px;
  margin: 0 auto var(--spacing-xl);
  color: var(--primary-color);
  opacity: 0.8;
}

.error-icon svg {
  width: 100%;
  height: 100%;
}

.error-code {
  font-size: 72px;
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-sm);
  line-height: 1;
  letter-spacing: -2px;
}

.error-title {
  font-size: var(--font-size-extra-large);
  font-weight: var(--font-weight-medium);
  color: var(--text-regular);
  margin: 0 0 var(--spacing-lg);
}

.error-description {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-2xl);
  line-height: var(--line-height-normal);
}

.error-actions {
  display: flex;
  gap: var(--spacing-md);
  justify-content: center;
}

/* 响应式 */
@media (max-width: 768px) {
  .error-icon {
    width: 80px;
    height: 80px;
  }

  .error-code {
    font-size: 48px;
  }

  .error-title {
    font-size: var(--font-size-large);
  }

  .error-actions {
    flex-direction: column;
  }
}
</style>

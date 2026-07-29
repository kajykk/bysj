<template>
  <div class="error-page">
    <div class="error-content">
      <!-- 状态标签 -->
      <div
        class="error-status-tag"
        :class="`error-status-tag--${errorType}`"
      >
        {{ code }}
      </div>

      <!-- 错误代码 -->
      <h1
        class="error-code"
        :class="`error-code--${errorType}`"
      >
        {{ code }}
      </h1>

      <!-- 错误图标 -->
      <div
        class="error-icon"
        :class="`error-icon--${errorType}`"
      >
        <svg
          v-if="code === '404'"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <circle
            cx="12"
            cy="12"
            r="10"
          />
          <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
        </svg>
        <svg
          v-else-if="code === '403'"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
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
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          <line
            x1="12"
            y1="9"
            x2="12"
            y2="13"
          />
          <line
            x1="12"
            y1="17"
            x2="12.01"
            y2="17"
          />
        </svg>
        <svg
          v-else
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
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
        <slot name="actions">
          <el-button
            type="primary"
            size="large"
            :icon="HomeFilled"
            @click="goHome"
          >
            {{ t('error.goHome') }}
          </el-button>
          <el-button
            v-if="showBack"
            size="large"
            :icon="Back"
            @click="goBack"
          >
            {{ t('error.goBack') }}
          </el-button>
        </slot>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { HomeFilled, Back } from '@element-plus/icons-vue'

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

const errorType = computed(() => {
  switch (props.code) {
    case '404': return 'info'
    case '403': return 'warning'
    case '500': return 'danger'
    default: return 'info'
  }
})

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
.error-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: var(--spacing-xl);
  background: linear-gradient(
    135deg,
    var(--bg-page) 0%,
    var(--bg-hover) 100%
  );
}

.error-content {
  position: relative;
  text-align: center;
  max-width: 480px;
  background-color: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--spacing-2xl) var(--spacing-xl);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

/* ===== 状态标签 ===== */
.error-status-tag {
  position: absolute;
  top: var(--spacing-md);
  right: var(--spacing-md);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-xs);
  font-size: var(--font-size-extra-small);
  font-weight: var(--font-weight-medium);
  font-family: var(--font-family-mono, monospace);
  line-height: 1.6;
}

.error-status-tag--info {
  background-color: var(--info-light, var(--bg-page));
  color: var(--info-color, var(--text-secondary));
}

.error-status-tag--warning {
  background-color: var(--warning-light, var(--bg-page));
  color: var(--warning-color);
}

.error-status-tag--danger {
  background-color: var(--danger-light, var(--bg-page));
  color: var(--danger-color);
}

/* ===== 错误代码 ===== */
.error-code {
  font-size: 72px;
  font-weight: var(--font-weight-bold);
  margin: 0 0 var(--spacing-md);
  line-height: 1;
  letter-spacing: -0.03em;
}

.error-code--info {
  color: var(--primary-color);
}

.error-code--warning {
  color: var(--warning-color);
}

.error-code--danger {
  color: var(--danger-color);
}

/* ===== 错误图标 ===== */
.error-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto var(--spacing-md);
}

.error-icon svg {
  width: 100%;
  height: 100%;
}

.error-icon--info {
  color: var(--info-color, var(--text-secondary));
}

.error-icon--warning {
  color: var(--warning-color);
}

.error-icon--danger {
  color: var(--danger-color);
}

/* ===== 错误标题 ===== */
.error-title {
  font-size: var(--font-size-extra-large);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-sm);
}

/* ===== 错误描述 ===== */
.error-description {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-xl);
  line-height: var(--line-height-normal);
  max-width: 360px;
  margin-left: auto;
  margin-right: auto;
}

/* ===== 操作按钮 ===== */
.error-actions {
  display: flex;
  gap: var(--spacing-sm);
  justify-content: center;
}

/* ===== 响应式 ===== */
@media (max-width: 768px) {
  .error-code {
    font-size: 56px;
  }

  .error-title {
    font-size: var(--font-size-large);
  }

  .error-actions {
    flex-direction: column;
    width: 100%;
  }

  .error-actions .el-button {
    width: 100%;
  }
}
</style>

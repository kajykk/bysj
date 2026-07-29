<template>
  <div
    ref="containerRef"
    class="lazy-image-container"
    :style="containerStyle"
  >
    <!-- 骨架占位 / 加载中 -->
    <div
      v-if="!isLoaded && !hasError"
      class="lazy-image-placeholder"
    >
      <slot name="placeholder">
        <div class="lazy-image-skeleton">
          <svg
            class="lazy-image-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect
              x="3"
              y="3"
              width="18"
              height="18"
              rx="2"
              ry="2"
            />
            <circle
              cx="8.5"
              cy="8.5"
              r="1.5"
            />
            <polyline points="21 15 16 10 5 21" />
          </svg>
          <div
            v-if="isLoading"
            class="lazy-image-progress-bar"
          />
        </div>
      </slot>
    </div>

    <!-- 响应式图片 (picture + srcset) -->
    <picture v-if="isVisible && responsive">
      <source
        v-for="(source, index) in pictureSources"
        :key="index"
        :srcset="source.srcset"
        :type="source.type"
      >
      <img
        ref="imgRef"
        :src="src"
        :srcset="imgSrcSet"
        :sizes="sizes"
        :alt="alt"
        :class="['lazy-image-img', { 'lazy-image-fade-in': isLoaded }]"
        :style="imgStyle"
        @load="handleLoad"
        @error="handleError"
      >
    </picture>

    <!-- 普通图片 -->
    <img
      v-else-if="isVisible"
      ref="imgRef"
      :src="src"
      :alt="alt"
      :class="['lazy-image-img', { 'lazy-image-fade-in': isLoaded }]"
      :style="imgStyle"
      @load="handleLoad"
      @error="handleError"
    >

    <!-- 错误状态 -->
    <div
      v-if="hasError"
      class="lazy-image-error"
    >
      <slot name="error">
        <div class="lazy-image-default-error">
          <svg
            class="lazy-image-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect
              x="3"
              y="3"
              width="18"
              height="18"
              rx="2"
              ry="2"
            />
            <line
              x1="9"
              y1="9"
              x2="15"
              y2="15"
            />
            <line
              x1="15"
              y1="9"
              x2="9"
              y2="15"
            />
          </svg>
          <span class="lazy-image-error-text">{{ t('common.loadFailed') }}</span>
          <button
            class="lazy-image-retry-btn"
            type="button"
            @click="handleRetry"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
            </svg>
            <span>{{ t('common.retry') }}</span>
          </button>
        </div>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { generateSrcSet, generatePictureSources } from '@/utils/imageOptimizer'

interface Props {
  src: string
  alt?: string
  width?: string | number
  height?: string | number
  objectFit?: 'contain' | 'cover' | 'fill' | 'none' | 'scale-down'
  rootMargin?: string
  threshold?: number
  responsive?: boolean
  sizes?: string
}

const props = withDefaults(defineProps<Props>(), {
  alt: '',
  width: 'auto',
  height: 'auto',
  objectFit: 'cover',
  rootMargin: '50px',
  threshold: 0,
  responsive: false,
  sizes: '100vw',
})

const emit = defineEmits<{
  load: []
  error: [Event]
}>()

const { t } = useI18n()

const containerRef = ref<HTMLDivElement>()
const imgRef = ref<HTMLImageElement>()
const isVisible = ref(false)
const isLoading = ref(false)
const isLoaded = ref(false)
const hasError = ref(false)

let observer: IntersectionObserver | null = null

const containerStyle = computed(() => {
  const style: Record<string, string> = {}
  if (props.width) {
    style.width = typeof props.width === 'number' ? `${props.width}px` : props.width
  }
  if (props.height) {
    style.height = typeof props.height === 'number' ? `${props.height}px` : props.height
  }
  return style
})

const imgStyle = computed(() => ({
  objectFit: props.objectFit,
  width: '100%',
  height: '100%',
}))

const pictureSources = computed(() => {
  if (!props.responsive) return []
  return generatePictureSources(props.src)
})

const imgSrcSet = computed(() => {
  if (!props.responsive) return undefined
  return generateSrcSet(props.src)
})

const handleLoad = () => {
  isLoaded.value = true
  isLoading.value = false
  emit('load')
}

const handleError = (e: Event) => {
  isLoading.value = false
  hasError.value = true
  emit('error', e)
}

const handleRetry = () => {
  hasError.value = false
  isLoaded.value = false
  isVisible.value = false
  isLoading.value = false
  setupObserver()
}

const setupObserver = () => {
  if (!containerRef.value) return

  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          isVisible.value = true
          isLoading.value = true
          if (observer && containerRef.value) {
            observer.unobserve(containerRef.value)
          }
        }
      })
    },
    {
      rootMargin: props.rootMargin,
      threshold: props.threshold,
    }
  )

  observer.observe(containerRef.value)
}

onMounted(() => {
  if ('IntersectionObserver' in window) {
    setupObserver()
  } else {
    isVisible.value = true
    isLoading.value = true
  }
})

onUnmounted(() => {
  if (observer && containerRef.value) {
    observer.unobserve(containerRef.value)
    observer.disconnect()
  }
})

defineExpose({
  reload: handleRetry,
})
</script>

<style scoped>
.lazy-image-container {
  position: relative;
  display: inline-block;
  overflow: hidden;
  background-color: var(--bg-page);
}

.lazy-image-placeholder,
.lazy-image-error {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ===== 骨架占位（shimmer 动画，与 SkeletonScreen / transitions.scss 一致） ===== */
.lazy-image-skeleton {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(
    90deg,
    var(--border-light) 25%,
    var(--bg-page) 50%,
    var(--border-light) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s infinite;
}

.lazy-image-icon {
  width: 32px;
  height: 32px;
  color: var(--text-placeholder);
  opacity: 0.6;
}

.lazy-image-progress-bar {
  position: absolute;
  bottom: 0;
  left: 20%;
  width: 60%;
  height: 2px;
  background-color: var(--primary-color);
  animation: progress-slide 1.2s ease-in-out infinite;
}

@keyframes progress-slide {
  0% {
    transform: translateX(-30%);
    opacity: 0.6;
  }
  50% {
    opacity: 1;
  }
  100% {
    transform: translateX(30%);
    opacity: 0.6;
  }
}

/* ===== 错误状态 ===== */
.lazy-image-default-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
}

.lazy-image-default-error .lazy-image-icon {
  color: var(--text-placeholder);
}

.lazy-image-error-text {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.lazy-image-retry-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-xs);
  padding: 0 var(--spacing-sm);
  height: 28px;
  border: 1px solid var(--primary-color);
  border-radius: var(--radius-xs);
  background-color: transparent;
  color: var(--primary-color);
  font-size: var(--font-size-extra-small);
  cursor: pointer;
  transition: background-color var(--transition-duration, 0.2s) ease;
}

.lazy-image-retry-btn svg {
  width: 12px;
  height: 12px;
}

.lazy-image-retry-btn:hover {
  background-color: var(--bg-active);
}

.lazy-image-retry-btn:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

/* ===== 图片渐入 ===== */
.lazy-image-img {
  display: block;
  opacity: 0;
  transition: opacity 0.3s var(--transition-ease-out, ease);
}

.lazy-image-fade-in {
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .lazy-image-skeleton {
    animation: none;
  }

  .lazy-image-progress-bar {
    animation: none;
    opacity: 0.6;
  }

  .lazy-image-img {
    transition: none;
    opacity: 1;
  }
}
</style>

<template>
  <div
    ref="containerRef"
    class="lazy-image-container"
    :style="containerStyle"
  >
    <!-- 占位图 / 加载中 -->
    <div
      v-if="!isLoaded"
      class="lazy-image-placeholder"
      :class="{ 'lazy-image-loading': isLoading }"
    >
      <slot name="placeholder">
        <div class="lazy-image-default-placeholder">
          <svg
            class="lazy-image-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
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
          <span class="lazy-image-error-text">加载失败</span>
        </div>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
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

const setupObserver = () => {
  if (!containerRef.value) return

  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          isVisible.value = true
          isLoading.value = true
          // 停止观察，图片只需加载一次
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
  // 检查浏览器是否支持 IntersectionObserver
  if ('IntersectionObserver' in window) {
    setupObserver()
  } else {
    // 降级：直接加载图片
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

// 暴露方法供外部调用
defineExpose({
  reload: () => {
    hasError.value = false
    isLoaded.value = false
    isVisible.value = false
    isLoading.value = false
    setupObserver()
  },
})
</script>

<style scoped>
.lazy-image-container {
  position: relative;
  display: inline-block;
  overflow: hidden;
  background-color: #f5f7fa;
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

.lazy-image-default-placeholder,
.lazy-image-default-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
}

.lazy-image-loading .lazy-image-default-placeholder {
  animation: lazyImagePulse 1.5s ease-in-out infinite;
}

.lazy-image-icon {
  width: 32px;
  height: 32px;
}

.lazy-image-error-text {
  margin-top: 8px;
  font-size: 12px;
  color: #f56c6c;
}

.lazy-image-img {
  display: block;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.lazy-image-fade-in {
  opacity: 1;
}

@keyframes lazyImagePulse {
  0%,
  100% {
    opacity: 0.6;
  }
  50% {
    opacity: 1;
  }
}
</style>

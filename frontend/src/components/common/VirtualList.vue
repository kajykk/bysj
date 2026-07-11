<template>
  <div
    ref="containerRef"
    class="virtual-list-container"
    :style="containerStyle"
    @scroll="handleScroll"
  >
    <div
      class="virtual-list-phantom"
      :style="phantomStyle"
    />
    <div
      class="virtual-list-content"
      :style="contentStyle"
    >
      <div
        v-for="item in visibleItems"
        :key="getItemKey(item.item, item.index)"
        class="virtual-list-item"
        :style="getItemStyle(item.index)"
      >
        <slot
          :item="item.item"
          :index="item.index"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts" generic="T extends Record<string, unknown>">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'

const props = withDefaults(defineProps<{
  items: T[]
  itemHeight: number
  buffer?: number
  containerHeight?: number
  keyField?: keyof T | string
}>(), {
  buffer: 5,
  containerHeight: 400,
  keyField: 'id' as keyof T | string,
})

const containerRef = ref<HTMLDivElement>()
const scrollTop = ref(0)
const containerWidth = ref(0)

const totalHeight = computed(() => props.items.length * props.itemHeight)

const startIndex = computed(() => {
  const idx = Math.floor(scrollTop.value / props.itemHeight)
  return Math.max(0, idx - props.buffer)
})

const visibleCount = computed(() => {
  if (!containerRef.value) return 0
  const count = Math.ceil(props.containerHeight / props.itemHeight)
  return count + props.buffer * 2
})

const endIndex = computed(() => {
  const idx = startIndex.value + visibleCount.value
  return Math.min(props.items.length, idx)
})

const visibleItems = computed(() => {
  const result: { item: T; index: number }[] = []
  for (let i = startIndex.value; i < endIndex.value; i++) {
    if (i < props.items.length) {
      result.push({ item: props.items[i], index: i })
    }
  }
  return result
})

const offsetY = computed(() => startIndex.value * props.itemHeight)

const containerStyle = computed(() => ({
  height: `${props.containerHeight}px`,
  overflow: 'auto',
  position: 'relative' as const,
}))

const phantomStyle = computed(() => ({
  height: `${totalHeight.value}px`,
  width: '1px',
}))

const contentStyle = computed(() => ({
  position: 'absolute' as const,
  top: '0',
  left: '0',
  right: '0',
  transform: `translateY(${offsetY.value}px)`,
  willChange: 'transform',
}))

const getItemStyle = (_index: number) => ({
  height: `${props.itemHeight}px`,
  boxSizing: 'border-box' as const,
})

const getItemKey = (item: T, index: number): string | number => {
  if (props.keyField && props.keyField in item) {
    return item[props.keyField] as string | number
  }
  return index
}

let scrollTimer: ReturnType<typeof requestAnimationFrame> | null = null

const handleScroll = (e: Event) => {
  const target = e.target as HTMLDivElement
  if (scrollTimer) {
    cancelAnimationFrame(scrollTimer)
  }
  scrollTimer = requestAnimationFrame(() => {
    scrollTop.value = target.scrollTop
  })
}

const scrollToIndex = (index: number) => {
  if (!containerRef.value) return
  const targetScrollTop = index * props.itemHeight
  containerRef.value.scrollTop = targetScrollTop
  scrollTop.value = targetScrollTop
}

const scrollToTop = () => {
  scrollToIndex(0)
}

const scrollToBottom = () => {
  scrollToIndex(Math.max(0, props.items.length - 1))
}

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (containerRef.value) {
    containerWidth.value = containerRef.value.clientWidth
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        containerWidth.value = entry.contentRect.width
      }
    })
    resizeObserver.observe(containerRef.value)
  }
})

onUnmounted(() => {
  // P1-D-9 修复：调用 disconnect() 释放 ResizeObserver 所有资源，而非仅 unobserve
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (scrollTimer) {
    cancelAnimationFrame(scrollTimer)
  }
})

watch(() => props.items.length, () => {
  nextTick(() => {
    if (containerRef.value) {
      const maxScrollTop = Math.max(0, totalHeight.value - props.containerHeight)
      if (scrollTop.value > maxScrollTop) {
        scrollTop.value = maxScrollTop
        containerRef.value.scrollTop = maxScrollTop
      }
    }
  })
})

defineExpose({
  scrollToIndex,
  scrollToTop,
  scrollToBottom,
  containerRef,
})
</script>

<style scoped>
.virtual-list-container {
  width: 100%;
}

.virtual-list-phantom {
  position: absolute;
  top: 0;
  left: 0;
  z-index: -1;
}

.virtual-list-content {
  width: 100%;
}

.virtual-list-item {
  width: 100%;
}
</style>

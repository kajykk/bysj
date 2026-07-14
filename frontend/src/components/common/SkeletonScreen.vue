<template>
  <div
    class="skeleton-screen"
    :class="{ 'skeleton-animate': animate }"
  >
    <div
      v-for="i in rows"
      :key="i"
      class="skeleton-row"
      :style="{ height: `${rowHeight}px` }"
    >
      <div
        class="skeleton-item"
        :style="{ width: `${getRandomWidth(i)}%` }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  rows?: number
  rowHeight?: number
  animate?: boolean
}

withDefaults(defineProps<Props>(), {
  rows: 5,
  rowHeight: 20,
  animate: true,
})

const getRandomWidth = (index: number) => {
  // Generate deterministic pseudo-random widths
  const widths = [40, 60, 80, 50, 90, 30, 70, 45, 85, 55]
  return widths[index % widths.length]
}
</script>

<style scoped>
.skeleton-screen {
  width: 100%;
}

.skeleton-row {
  display: flex;
  align-items: center;
  padding: var(--spacing-xs) 0;
}

.skeleton-item {
  height: 100%;
  background-color: var(--border-light);
  border-radius: var(--radius-xs);
}

/* 与全局 skeleton 动画（transitions.scss / index.html 内联）保持一致，
   使用设计令牌，避免独立的 opacity 脉冲造成视觉割裂 */
.skeleton-animate .skeleton-item {
  background: linear-gradient(
    90deg,
    var(--border-light) 25%,
    var(--bg-page) 50%,
    var(--border-light) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s infinite;
}
</style>

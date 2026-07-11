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
  padding: 8px 0;
}

.skeleton-item {
  height: 100%;
  background-color: #f0f2f5;
  border-radius: 4px;
}

.skeleton-animate .skeleton-item {
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

@keyframes skeleton-pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}
</style>

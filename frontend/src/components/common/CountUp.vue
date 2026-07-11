<template>
  <span class="count-up">{{ displayValue }}</span>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'

interface Props {
  end: number
  start?: number
  duration?: number
  decimals?: number
  prefix?: string
  suffix?: string
  separator?: string
  useEasing?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  start: 0,
  duration: 2000,
  decimals: 0,
  prefix: '',
  suffix: '',
  separator: ',',
  useEasing: true,
})

const displayValue = ref(props.prefix + formatNumber(props.start) + props.suffix)
let animationId: number | null = null

function formatNumber(num: number): string {
  const fixed = num.toFixed(props.decimals)
  const parts = fixed.split('.')
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, props.separator)
  return parts.join('.')
}

function easeOutQuart(t: number): number {
  return 1 - Math.pow(1 - t, 4)
}

function animate() {
  if (animationId !== null) {
    cancelAnimationFrame(animationId)
  }

  const startTime = performance.now()
  const startValue = props.start
  const endValue = props.end
  const diff = endValue - startValue

  function step(currentTime: number) {
    const elapsed = currentTime - startTime
    const progress = Math.min(elapsed / props.duration, 1)
    const easedProgress = props.useEasing ? easeOutQuart(progress) : progress
    const currentValue = startValue + diff * easedProgress

    displayValue.value = props.prefix + formatNumber(currentValue) + props.suffix

    if (progress < 1) {
      animationId = requestAnimationFrame(step)
    }
  }

  animationId = requestAnimationFrame(step)
}

onMounted(() => {
  animate()
})

watch(() => props.end, () => {
  animate()
})

// P1-D-9 修复：组件卸载时取消未完成的动画帧，防止内存泄漏
onBeforeUnmount(() => {
  if (animationId !== null) {
    cancelAnimationFrame(animationId)
    animationId = null
  }
})
</script>

<style scoped>
.count-up {
  font-variant-numeric: tabular-nums;
}
</style>

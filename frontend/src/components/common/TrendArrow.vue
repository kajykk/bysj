<template>
  <span
    v-if="prev !== null && prev !== undefined"
    class="trend-arrow"
    :class="trendClass"
  >
    <el-icon v-if="trend === 'up'"><ArrowUp /></el-icon>
    <el-icon v-else-if="trend === 'down'"><ArrowDown /></el-icon>
    <el-icon v-else><Minus /></el-icon>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUp, ArrowDown, Minus } from '@element-plus/icons-vue'

const props = defineProps<{
  value: number
  prev?: number | null | undefined
}>()

const trend = computed(() => {
  if (props.prev === null || props.prev === undefined) return 'same'
  const diff = props.value - props.prev
  if (Math.abs(diff) < 0.01) return 'same'
  return diff > 0 ? 'up' : 'down'
})

const trendClass = computed(() => {
  return {
    'trend-up': trend.value === 'up',
    'trend-down': trend.value === 'down',
    'trend-same': trend.value === 'same'
  }
})
</script>

<style scoped>
.trend-arrow {
  margin-left: 4px;
  font-size: 12px;
}

.trend-up {
  color: #f56c6c;
}

.trend-down {
  color: #67c23a;
}

.trend-same {
  color: #909399;
}
</style>

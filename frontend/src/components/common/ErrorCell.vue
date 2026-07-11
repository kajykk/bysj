<template>
  <span
    v-if="message"
    class="error-cell"
  >{{ message }}</span>
  <span
    v-else
    class="placeholder"
  >{{ placeholder }}</span>
</template>

<script setup lang="ts">
defineProps<{
  message?: string
  placeholder?: string
}>()
</script>

<style scoped>
.error-cell {
  color: #f56c6c;
}

.placeholder {
  color: #909399;
}
</style>

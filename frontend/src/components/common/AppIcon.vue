<template>
  <Icon
    :icon="resolvedName"
    class="app-icon"
    :width="size"
    :height="size"
    aria-hidden="true"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Icon } from '@iconify/vue'
import '@/icons'

const props = withDefaults(defineProps<{
  name: string
  size?: string | number
}>(), {
  size: '1em',
})

const resolvedName = computed(() =>
  props.name.includes(':') ? props.name : `tabler:${props.name}`,
)
</script>

<style scoped>
.app-icon {
  display: inline-block;
  flex-shrink: 0;
  vertical-align: -0.125em;
}
</style>

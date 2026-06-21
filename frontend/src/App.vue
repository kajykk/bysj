<template>
  <div
    v-loading.fullscreen.lock="loadingStore.isLoading"
    class="app-root"
    :element-loading-text="loadingStore.loadingText"
  >
    <router-view />
  </div>
</template>

<script setup lang="ts">
import { useLoadingStore } from '@/stores/loading'

const loadingStore = useLoadingStore()
</script>

<style scoped>
.app-root {
  min-height: 100vh;
}
</style>

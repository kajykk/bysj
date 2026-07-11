<template>
  <BentoCell
    :title="title"
    class="list-scaffold"
  >
    <template #actions>
      <slot name="header-extra" />
    </template>

    <slot name="filters" />

    <StatefulContainer
      :loading="loading"
      :empty="empty"
      :error-message="errorMessage"
      :empty-text="emptyText"
      @retry="$emit('retry')"
    >
      <slot />
    </StatefulContainer>
  </BentoCell>
</template>

<script setup lang="ts">
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import BentoCell from '@/components/common/BentoCell.vue'

defineProps<{
  title: string
  loading: boolean
  empty: boolean
  errorMessage?: string
  emptyText?: string
}>()

defineEmits<{
  retry: []
}>()
</script>

<style scoped>
/* BentoCell 已提供容器视觉；此处仅微调列表场景的间距 */
/* ISS-102 修复：硬编码间距改用设计令牌 */
.list-scaffold {
  padding: var(--spacing-md);
}

.list-scaffold :deep(.bento-cell__body) {
  gap: var(--spacing-sm);
}
</style>

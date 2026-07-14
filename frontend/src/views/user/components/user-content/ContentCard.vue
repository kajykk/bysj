<template>
  <el-card
    shadow="hover"
    class="content-card"
    @click="emit('open-detail', item)"
  >
    <div class="card-body">
      <h4 class="content-title">
        {{ item.title }}
      </h4>
      <p class="content-summary">
        {{ item.summary || t('userContent.noSummary') }}
      </p>
      <div class="content-meta">
        <el-tag size="small">
          {{ contentTypeLabel }}
        </el-tag>
        <el-tag
          v-if="item.category"
          size="small"
          type="info"
        >
          {{ item.category }}
        </el-tag>
        <span
          v-if="showDuration && item.duration_minutes"
          class="meta-text"
        >{{ t('userContent.durationMinutes', { count: item.duration_minutes }) }}</span>
      </div>
      <div
        v-if="variant === 'recommendations' && item.recommend_reason"
        class="recommend-reason"
      >
        <el-tag
          type="success"
          size="small"
          effect="light"
        >
          {{ t('userContent.recommendReason', { reason: item.recommend_reason }) }}
        </el-tag>
      </div>
      <div
        class="content-actions"
        @click.stop
      >
        <el-button
          :type="buttonType"
          size="small"
          link
          @click="emit('toggle-favorite', item)"
        >
          {{ buttonText }}
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ContentItem } from '@/api/userApi'
import { CONTENT_TYPE_LABEL_KEYS } from './sharedContentUtils'

const props = defineProps<{
  item: ContentItem
  variant: 'browse' | 'favorites' | 'recommendations'
}>()

const emit = defineEmits<{
  (e: 'open-detail', item: ContentItem): void
  (e: 'toggle-favorite', item: ContentItem): void
}>()

const { t } = useI18n()

const showDuration = computed(() => props.variant === 'browse')

const contentTypeLabel = computed(() => {
  const key = CONTENT_TYPE_LABEL_KEYS[props.item.content_type]
  return key ? t(`userContent.${key}`) : props.item.content_type
})

const buttonType = computed(() => {
  if (props.variant === 'favorites') return 'warning'
  return props.item.is_favorited ? 'warning' : 'default'
})

const buttonText = computed(() => {
  if (props.variant === 'favorites') return t('userContent.unfavorite')
  return props.item.is_favorited ? t('userContent.favorited') : t('userContent.favorite')
})
</script>

<style scoped>
.content-card {
  cursor: pointer;
  transition: transform var(--transition-fast) var(--transition-ease-out);
}
.content-card:hover {
  transform: translateY(-2px);
}
.card-body {
  min-height: 140px;
  display: flex;
  flex-direction: column;
}
.content-title {
  margin: 0 0 var(--spacing-sm);
  font-size: var(--font-size-base);
  line-height: 1.4;
}
.content-summary {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  margin: 0 0 var(--spacing-md);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.content-meta {
  display: flex;
  gap: var(--spacing-xs);
  align-items: center;
  flex-wrap: wrap;
}
.meta-text {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
.content-actions {
  margin-top: var(--spacing-sm);
}
.recommend-reason {
  margin-top: var(--spacing-xs);
}
</style>

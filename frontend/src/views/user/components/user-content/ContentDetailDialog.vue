<template>
  <el-dialog
    :model-value="visible"
    :title="data?.title || t('userContent.detailTitle')"
    width="700px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <div
      v-if="loading"
      class="skeleton-padding"
    >
      <el-skeleton
        :rows="6"
        animated
      />
    </div>
    <template v-else-if="data">
      <div class="detail-meta">
        <el-tag size="small">
          {{ contentTypeLabel }}
        </el-tag>
        <el-tag
          v-if="data.category"
          size="small"
          type="info"
        >
          {{ data.category }}
        </el-tag>
        <span
          v-if="data.duration_minutes"
          class="meta-text"
        >{{ t('userContent.durationMinutes', { count: data.duration_minutes }) }}</span>
        <span
          v-if="data.view_count"
          class="meta-text"
        >{{ t('userContent.viewCount', { count: data.view_count }) }}</span>
      </div>
      <el-divider />
      <!-- eslint-disable vue/no-v-html -- 内容已通过 DOMPurify 白名单净化，允许展示受控富文本 -->
      <div
        class="detail-content"
        v-html="sanitizedHtml"
      />
      <!-- eslint-enable vue/no-v-html -->
      <div
        v-if="data.audio_url"
        class="audio-wrapper"
      >
        <audio
          controls
          :src="data.audio_url"
          class="audio-player"
        />
      </div>
    </template>
    <template #footer>
      <el-button
        v-if="data"
        :type="data.is_favorited ? 'warning' : 'default'"
        @click="handleToggle"
      >
        {{ data?.is_favorited ? t('userContent.unfavorite') : t('userContent.favorite') }}
      </el-button>
      <el-button @click="emit('close')">
        {{ t('common.close') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ContentItem, ContentDetail } from '@/api/userApi'
import { CONTENT_TYPE_LABEL_KEYS } from './sharedContentUtils'

const props = defineProps<{
  visible: boolean
  data: ContentDetail | null
  loading: boolean
  sanitizedHtml: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'close'): void
  (e: 'toggle-favorite', item: ContentItem): void
}>()

const { t } = useI18n()

const contentTypeLabel = computed(() => {
  if (!props.data) return ''
  const key = CONTENT_TYPE_LABEL_KEYS[props.data.content_type]
  return key ? t(`userContent.${key}`) : props.data.content_type
})

const handleToggle = () => {
  if (props.data) {
    emit('toggle-favorite', props.data)
  }
}
</script>

<style scoped>
.detail-meta {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
  flex-wrap: wrap;
}
.meta-text {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}
.detail-content {
  line-height: 1.8;
  font-size: var(--font-size-base);
}
.detail-content :deep(img) {
  max-width: 100%;
  height: auto;
}

.skeleton-padding {
  padding: var(--spacing-xl);
}

.audio-wrapper {
  margin-top: var(--spacing-lg);
}

.audio-player {
  width: 100%;
}

/* 响应式：移动端适配 */
@media (max-width: 768px) {
  :deep(.el-dialog) {
    width: 92% !important;
  }
}
</style>

<template>
  <div class="content-page">
    <el-tabs
      v-model="activeTab"
      type="border-card"
      @tab-change="handleTabChange"
    >
      <el-tab-pane
        :label="t('userContent.tabBrowse')"
        name="browse"
      >
        <FilterBar
          @search="loadContents"
          @reset="handleResetBrowse"
        >
          <el-form-item :label="t('userContent.filterCategory')">
            <el-select
              v-model="browseFilters.category"
              clearable
              style="width: 140px"
            >
              <el-option
                :label="t('userContent.categoryEmotion')"
                value="emotion"
              />
              <el-option
                :label="t('userContent.categoryStress')"
                value="stress"
              />
              <el-option
                :label="t('userContent.categoryMindfulness')"
                value="mindfulness"
              />
              <el-option
                :label="t('userContent.categoryCrisis')"
                value="crisis"
              />
              <el-option
                :label="t('userContent.categoryWellbeing')"
                value="wellbeing"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('userContent.filterType')">
            <el-select
              v-model="browseFilters.content_type"
              clearable
              style="width: 140px"
            >
              <el-option
                :label="t('userContent.typeArticle')"
                value="article"
              />
              <el-option
                :label="t('userContent.typeAudio')"
                value="audio"
              />
              <el-option
                :label="t('userContent.typeVideo')"
                value="video"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('userContent.filterSearch')">
            <el-input
              v-model="browseFilters.keyword"
              clearable
              :placeholder="t('userContent.keywordPlaceholder')"
              style="width: 160px"
            />
          </el-form-item>
        </FilterBar>

        <StatefulContainer
          :loading="browseLoading"
          :empty="!browseLoading && browseRows.length === 0"
          :error-message="browseError"
          :empty-text="t('userContent.emptyBrowse')"
          @retry="loadContents"
        >
          <el-row :gutter="16">
            <el-col
              v-for="item in browseRows"
              :key="item.id"
              :xs="24"
              :sm="12"
              :md="8"
              class="content-col"
            >
              <el-card
                shadow="hover"
                class="content-card"
                @click="openDetail(item)"
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
                      {{ contentTypeLabel(item.content_type) }}
                    </el-tag>
                    <el-tag
                      v-if="item.category"
                      size="small"
                      type="info"
                    >
                      {{ item.category }}
                    </el-tag>
                    <span
                      v-if="item.duration_minutes"
                      class="meta-text"
                    >{{ t('userContent.durationMinutes', { count: item.duration_minutes }) }}</span>
                  </div>
                  <div
                    class="content-actions"
                    @click.stop
                  >
                    <el-button
                      :type="item.is_favorited ? 'warning' : 'default'"
                      size="small"
                      link
                      @click="handleToggleFavorite(item)"
                    >
                      {{ item.is_favorited ? t('userContent.favorited') : t('userContent.favorite') }}
                    </el-button>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </StatefulContainer>
      </el-tab-pane>

      <el-tab-pane
        :label="t('userContent.tabFavorites')"
        name="favorites"
      >
        <StatefulContainer
          :loading="favLoading"
          :empty="!favLoading && favRows.length === 0"
          :error-message="favError"
          :empty-text="t('userContent.emptyFavorites')"
          @retry="loadFavorites"
        >
          <el-row :gutter="16">
            <el-col
              v-for="item in favRows"
              :key="item.id"
              :xs="24"
              :sm="12"
              :md="8"
              class="content-col"
            >
              <el-card
                shadow="hover"
                class="content-card"
                @click="openDetail(item)"
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
                      {{ contentTypeLabel(item.content_type) }}
                    </el-tag>
                    <el-tag
                      v-if="item.category"
                      size="small"
                      type="info"
                    >
                      {{ item.category }}
                    </el-tag>
                  </div>
                  <div
                    class="content-actions"
                    @click.stop
                  >
                    <el-button
                      type="warning"
                      size="small"
                      link
                      @click="handleToggleFavorite(item, true)"
                    >
                      {{ t('userContent.unfavorite') }}
                    </el-button>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </StatefulContainer>
      </el-tab-pane>

      <el-tab-pane
        :label="t('userContent.tabRecommendations')"
        name="recommendations"
      >
        <StatefulContainer
          :loading="recLoading"
          :empty="!recLoading && recRows.length === 0"
          :error-message="recError"
          :empty-text="t('userContent.emptyRecommendations')"
          @retry="loadRecommendations"
        >
          <el-row :gutter="16">
            <el-col
              v-for="item in recRows"
              :key="item.id"
              :xs="24"
              :sm="12"
              :md="8"
              class="content-col"
            >
              <el-card
                shadow="hover"
                class="content-card"
                @click="openDetail(item)"
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
                      {{ contentTypeLabel(item.content_type) }}
                    </el-tag>
                    <el-tag
                      v-if="item.category"
                      size="small"
                      type="info"
                    >
                      {{ item.category }}
                    </el-tag>
                  </div>
                  <div
                    v-if="item.recommend_reason"
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
                      :type="item.is_favorited ? 'warning' : 'default'"
                      size="small"
                      link
                      @click="handleToggleFavorite(item)"
                    >
                      {{ item.is_favorited ? t('userContent.favorited') : t('userContent.favorite') }}
                    </el-button>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </StatefulContainer>
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="detailVisible"
      :title="detailData?.title || t('userContent.detailTitle')"
      width="700px"
      destroy-on-close
    >
      <div
        v-if="detailLoading"
        class="skeleton-padding"
      >
        <el-skeleton
          :rows="6"
          animated
        />
      </div>
      <template v-else-if="detailData">
        <div class="detail-meta">
          <el-tag size="small">
            {{ contentTypeLabel(detailData.content_type) }}
          </el-tag>
          <el-tag
            v-if="detailData.category"
            size="small"
            type="info"
          >
            {{ detailData.category }}
          </el-tag>
          <span
            v-if="detailData.duration_minutes"
            class="meta-text"
          >{{ t('userContent.durationMinutes', { count: detailData.duration_minutes }) }}</span>
          <span
            v-if="detailData.view_count"
            class="meta-text"
          >{{ t('userContent.viewCount', { count: detailData.view_count }) }}</span>
        </div>
        <el-divider />
        <!-- eslint-disable vue/no-v-html -- 内容已通过 DOMPurify 白名单净化，允许展示受控富文本 -->
        <div
          class="detail-content"
          v-html="sanitizedDetailHtml"
        />
        <!-- eslint-enable vue/no-v-html -->
        <div
          v-if="detailData.audio_url"
          class="audio-wrapper"
        >
          <audio
            controls
            :src="detailData.audio_url"
            class="audio-player"
          />
        </div>
      </template>
      <template #footer>
        <el-button
          v-if="detailData"
          :type="detailData.is_favorited ? 'warning' : 'default'"
          @click="handleToggleFavorite(detailData)"
        >
          {{ detailData?.is_favorited ? t('userContent.unfavorite') : t('userContent.favorite') }}
        </el-button>
        <el-button @click="closeDetail">
          {{ t('common.close') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import DOMPurify from 'dompurify'

// ISSUE-008 修复：显式白名单策略，避免默认配置过宽
// 心理健康内容系统仅需基础富文本标签，禁用 script/iframe/form 等危险标签
const DOMPURIFY_CONFIG = {
  ALLOWED_TAGS: [
    'p', 'br', 'strong', 'em', 'u', 's', 'sub', 'sup',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
    'a', 'img', 'hr',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'div', 'span',
  ],
  ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'class', 'target', 'rel', 'width', 'height'],
  ALLOW_DATA_ATTR: false,
  FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'input', 'style', 'link', 'meta'],
  FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'onsubmit', 'style', 'srcset'],
  ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i,
} as Record<string, unknown>
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import FilterBar from '@/components/common/FilterBar.vue'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import { userApi, type ContentItem, type ContentDetail } from '@/api/userApi'
import { showHttpFeedback } from '@/utils/httpFeedback'

const { t } = useI18n()

const activeTab = ref('browse')
const browseFilters = reactive({ category: '', content_type: '', keyword: '' })
const browseRows = ref<ContentItem[]>([])
const browseLoading = ref(false)
const browseError = ref('')

const favRows = ref<ContentItem[]>([])
const favLoading = ref(false)
const favError = ref('')

const recRows = ref<ContentItem[]>([])
const recLoading = ref(false)
const recError = ref('')

const detailVisible = ref(false)
const detailData = ref<ContentDetail | null>(null)
const detailLoading = ref(false)
const sanitizedDetailHtml = ref('')

const CONTENT_TYPE_LABEL_KEYS: Record<string, string> = {
  article: 'typeArticle',
  audio: 'typeAudio',
  video: 'typeVideo'
}
const contentTypeLabel = (type: string) => {
  const key = CONTENT_TYPE_LABEL_KEYS[type]
  return key ? t(`userContent.${key}`) : type
}

const loadContents = async () => {
  browseLoading.value = true
  browseError.value = ''
  try {
    const data = await userApi.listContents({ page: 1, page_size: 9, category: browseFilters.category || undefined, content_type: browseFilters.content_type || undefined, keyword: browseFilters.keyword || undefined })
    browseRows.value = data.items
  } catch (error) {
    browseError.value = showHttpFeedback(error, t('userContent.loadFailed')).detail
  } finally {
    browseLoading.value = false
  }
}

const loadFavorites = async () => {
  favLoading.value = true
  favError.value = ''
  try {
    const data = await userApi.listFavorites({ page: 1, page_size: 9 })
    favRows.value = data.items
  } catch (error) {
    favError.value = showHttpFeedback(error, t('userContent.favoritesLoadFailed')).detail
  } finally {
    favLoading.value = false
  }
}

const loadRecommendations = async () => {
  recLoading.value = true
  recError.value = ''
  try {
    const data = await userApi.listRecommendations({ page: 1, page_size: 9 })
    recRows.value = data.items
  } catch (error) {
    recError.value = showHttpFeedback(error, t('userContent.recommendationsLoadFailed')).detail
  } finally {
    recLoading.value = false
  }
}

const handleTabChange = (tab: string | number) => {
  if (tab === 'favorites' && favRows.value.length === 0) loadFavorites()
  if (tab === 'recommendations' && recRows.value.length === 0) loadRecommendations()
}

const closeDetail = () => {
  detailVisible.value = false
  detailData.value = null
  sanitizedDetailHtml.value = ''
}

const handleResetBrowse = () => {
  browseFilters.category = ''
  browseFilters.content_type = ''
  browseFilters.keyword = ''
  loadContents()
}

const handleToggleFavorite = async (item: ContentItem, reloadFav = false) => {
  try {
    await userApi.toggleFavorite(item.id)
    item.is_favorited = !item.is_favorited
    ElMessage.success(item.is_favorited ? t('userContent.favoriteSuccess') : t('userContent.unfavoriteSuccess'))
    if (reloadFav || activeTab.value === 'favorites') await loadFavorites()
  } catch (error) {
    showHttpFeedback(error, t('userContent.favoriteFailed'))
  }
}

const openDetail = async (item: ContentItem) => {
  detailVisible.value = true
  detailLoading.value = true
  detailData.value = null
  sanitizedDetailHtml.value = ''
  try {
    detailData.value = await userApi.getContentDetail(item.id)
    sanitizedDetailHtml.value = DOMPurify.sanitize(detailData.value.content || '', DOMPURIFY_CONFIG) as string
  } catch (error) {
    showHttpFeedback(error, t('userContent.detailLoadFailed'))
  } finally {
    detailLoading.value = false
  }
}

onMounted(loadContents)
</script>

<style scoped>
.content-col {
  margin-bottom: var(--spacing-lg);
}

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
.detail-meta {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
  flex-wrap: wrap;
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

<template>
  <div class="content-page">
    <el-tabs
      v-model="activeTab"
      type="border-card"
      @tab-change="handleTabChange"
    >
      <el-tab-pane
        label="内容浏览"
        name="browse"
      >
        <FilterBar
          @search="loadContents"
          @reset="handleResetBrowse"
        >
          <el-form-item label="分类">
            <el-select
              v-model="browseFilters.category"
              clearable
              style="width: 140px"
            >
              <el-option
                label="情绪管理"
                value="emotion"
              />
              <el-option
                label="压力缓解"
                value="stress"
              />
              <el-option
                label="正念冥想"
                value="mindfulness"
              />
              <el-option
                label="危机干预"
                value="crisis"
              />
              <el-option
                label="身心健康"
                value="wellbeing"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="类型">
            <el-select
              v-model="browseFilters.content_type"
              clearable
              style="width: 140px"
            >
              <el-option
                label="文章"
                value="article"
              />
              <el-option
                label="音频"
                value="audio"
              />
              <el-option
                label="视频"
                value="video"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="搜索">
            <el-input
              v-model="browseFilters.keyword"
              clearable
              placeholder="关键词"
              style="width: 160px"
            />
          </el-form-item>
        </FilterBar>

        <StatefulContainer
          :loading="browseLoading"
          :empty="!browseLoading && browseRows.length === 0"
          :error-message="browseError"
          empty-text="暂无内容"
          @retry="loadContents"
        >
          <el-row :gutter="16">
            <el-col
              v-for="item in browseRows"
              :key="item.id"
              :span="8"
              style="margin-bottom: 16px"
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
                    {{ item.summary || '暂无摘要' }}
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
                    >{{ item.duration_minutes }}分钟</span>
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
                      {{ item.is_favorited ? '已收藏' : '收藏' }}
                    </el-button>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </StatefulContainer>
      </el-tab-pane>

      <el-tab-pane
        label="我的收藏"
        name="favorites"
      >
        <StatefulContainer
          :loading="favLoading"
          :empty="!favLoading && favRows.length === 0"
          :error-message="favError"
          empty-text="暂无收藏内容"
          @retry="loadFavorites"
        >
          <el-row :gutter="16">
            <el-col
              v-for="item in favRows"
              :key="item.id"
              :span="8"
              style="margin-bottom: 16px"
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
                    {{ item.summary || '暂无摘要' }}
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
                      取消收藏
                    </el-button>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </StatefulContainer>
      </el-tab-pane>

      <el-tab-pane
        label="推荐内容"
        name="recommendations"
      >
        <StatefulContainer
          :loading="recLoading"
          :empty="!recLoading && recRows.length === 0"
          :error-message="recError"
          empty-text="暂无推荐内容"
          @retry="loadRecommendations"
        >
          <el-row :gutter="16">
            <el-col
              v-for="item in recRows"
              :key="item.id"
              :span="8"
              style="margin-bottom: 16px"
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
                    {{ item.summary || '暂无摘要' }}
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
                      推荐理由：{{ item.recommend_reason }}
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
                      {{ item.is_favorited ? '已收藏' : '收藏' }}
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
      :title="detailData?.title || '内容详情'"
      width="700px"
      destroy-on-close
    >
      <div
        v-if="detailLoading"
        style="padding: 20px"
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
          >{{ detailData.duration_minutes }}分钟</span>
          <span
            v-if="detailData.view_count"
            class="meta-text"
          >{{ detailData.view_count }}次浏览</span>
        </div>
        <el-divider />
        <div
          class="detail-content"
          v-html="sanitizedDetailHtml"
        />
        <div
          v-if="detailData.audio_url"
          style="margin-top: 16px"
        >
          <audio
            controls
            :src="detailData.audio_url"
            style="width: 100%"
          />
        </div>
      </template>
      <template #footer>
        <el-button
          v-if="detailData"
          :type="detailData.is_favorited ? 'warning' : 'default'"
          @click="handleToggleFavorite(detailData)"
        >
          {{ detailData?.is_favorited ? '取消收藏' : '收藏' }}
        </el-button>
        <el-button @click="closeDetail">
          关闭
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import DOMPurify from 'dompurify'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import FilterBar from '@/components/common/FilterBar.vue'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import { userApi, type ContentItem, type ContentDetail } from '@/api/userApi'
import { showHttpFeedback } from '@/utils/httpFeedback'

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

const contentTypeLabel = (type: string) => ({ article: '文章', audio: '音频', video: '视频' }[type] || type)

const loadContents = async () => {
  browseLoading.value = true
  browseError.value = ''
  try {
    const data = await userApi.listContents({ page: 1, page_size: 9, category: browseFilters.category || undefined, content_type: browseFilters.content_type || undefined, keyword: browseFilters.keyword || undefined })
    browseRows.value = data.items
  } catch (error) {
    browseError.value = showHttpFeedback(error, '内容加载失败').detail
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
    favError.value = showHttpFeedback(error, '收藏列表加载失败').detail
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
    recError.value = showHttpFeedback(error, '推荐内容加载失败').detail
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
    ElMessage.success(item.is_favorited ? '已收藏' : '已取消收藏')
    if (reloadFav || activeTab.value === 'favorites') await loadFavorites()
  } catch (error) {
    showHttpFeedback(error, '收藏操作失败')
  }
}

const openDetail = async (item: ContentItem) => {
  detailVisible.value = true
  detailLoading.value = true
  detailData.value = null
  sanitizedDetailHtml.value = ''
  try {
    detailData.value = await userApi.getContentDetail(item.id)
    sanitizedDetailHtml.value = DOMPurify.sanitize(detailData.value.content || '')
  } catch (error) {
    showHttpFeedback(error, '内容详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

onMounted(loadContents)
</script>

<style scoped>
.content-card {
  cursor: pointer;
  transition: transform 0.2s;
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
  margin: 0 0 8px;
  font-size: 15px;
  line-height: 1.4;
}
.content-summary {
  color: #909399;
  font-size: 13px;
  margin: 0 0 10px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.content-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.meta-text {
  font-size: 12px;
  color: #909399;
}
.content-actions {
  margin-top: 8px;
}
.recommend-reason {
  margin-top: 6px;
}
.detail-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.detail-content {
  line-height: 1.8;
  font-size: 14px;
}
.detail-content :deep(img) {
  max-width: 100%;
  height: auto;
}
</style>

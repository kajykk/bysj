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
              <ContentCard
                :item="item"
                variant="browse"
                @open-detail="openDetail"
                @toggle-favorite="handleToggleFavorite"
              />
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
              <ContentCard
                :item="item"
                variant="favorites"
                @open-detail="openDetail"
                @toggle-favorite="handleToggleFavorite"
              />
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
              <ContentCard
                :item="item"
                variant="recommendations"
                @open-detail="openDetail"
                @toggle-favorite="handleToggleFavorite"
              />
            </el-col>
          </el-row>
        </StatefulContainer>
      </el-tab-pane>
    </el-tabs>

    <ContentDetailDialog
      v-model:visible="detailVisible"
      :data="detailData"
      :loading="detailLoading"
      :sanitized-html="sanitizedDetailHtml"
      @close="closeDetail"
      @toggle-favorite="handleToggleFavorite"
    />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import FilterBar from '@/components/common/FilterBar.vue'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import ContentCard from './components/user-content/ContentCard.vue'
import ContentDetailDialog from './components/user-content/ContentDetailDialog.vue'
import { useUserContentData } from './components/user-content/useUserContentData'

const { t } = useI18n()

const {
  activeTab,
  browseFilters, browseRows, browseLoading, browseError,
  favRows, favLoading, favError,
  recRows, recLoading, recError,
  detailVisible, detailData, detailLoading, sanitizedDetailHtml,
  loadContents, loadFavorites, loadRecommendations,
  handleTabChange, closeDetail, handleResetBrowse, handleToggleFavorite, openDetail,
} = useUserContentData()
</script>

<style scoped>
.content-col {
  margin-bottom: var(--spacing-lg);
}
</style>

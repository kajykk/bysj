/**
 * UserContent 数据加载与状态管理 composable。
 * 从原 UserContentPage.vue 提取所有响应式状态、加载函数与详情/收藏操作逻辑，
 * 视图层下沉至 ContentCard 子组件，对话框 UI 下沉至 ContentDetailDialog 子组件。
 */
import DOMPurify from 'dompurify'
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { userApi, type ContentItem, type ContentDetail } from '@/api/userApi'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { DOMPURIFY_CONFIG } from './sharedContentUtils'

export function useUserContentData() {
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

  const handleToggleFavorite = async (item: ContentItem) => {
    try {
      await userApi.toggleFavorite(item.id)
      item.is_favorited = !item.is_favorited
      ElMessage.success(item.is_favorited ? t('userContent.favoriteSuccess') : t('userContent.unfavoriteSuccess'))
      // 原 reloadFav=true 仅在 favorites 卡片调用；此时 activeTab 必为 'favorites'，
      // 故 activeTab === 'favorites' 已覆盖该路径，行为保持一致。
      if (activeTab.value === 'favorites') await loadFavorites()
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

  return {
    activeTab,
    browseFilters, browseRows, browseLoading, browseError,
    favRows, favLoading, favError,
    recRows, recLoading, recError,
    detailVisible, detailData, detailLoading, sanitizedDetailHtml,
    loadContents, loadFavorites, loadRecommendations,
    handleTabChange, closeDetail, handleResetBrowse, handleToggleFavorite, openDetail,
  }
}

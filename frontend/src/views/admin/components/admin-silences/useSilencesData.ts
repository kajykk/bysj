/**
 * AdminSilences 数据加载与状态管理 composable。
 * 从原 AdminSilencesPage.vue 提取所有响应式状态、加载函数与对话框操作逻辑，
 * 表格渲染下沉至 SilencesTable 子组件，对话框 UI 下沉至 SilenceFormDialog 子组件。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { alertsApi, type SilenceCreatePayload, type SilenceItem } from '@/api/alertsApi'
import { useListQueryState } from '@/composables/useListQueryState'
import { showHttpFeedback } from '@/utils/httpFeedback'

export function useSilencesData() {
  const { t } = useI18n()

  const queryState = useListQueryState('as')

  const loading = ref(false)
  const rows = ref<SilenceItem[]>([])
  const total = ref(0)
  const pageError = ref('')
  const deleteLoadingId = ref<number | null>(null)
  const editLoadingId = ref<number | null>(null)
  const enableLoadingId = ref<number | null>(null)
  const activeSilences = ref<SilenceItem[]>([])

  const page = computed(() => queryState.page.value)
  const pageSize = computed(() => queryState.pageSize.value)

  const filters = reactive<{ isActive: boolean | '' }>({
    isActive: queryState.getString('is_active') === '' ? '' : queryState.getString('is_active') === 'true'
  })

  // 对话框状态
  const formVisible = ref(false)
  const formSaving = ref(false)
  // ISS-073: 编辑模式状态
  const isEditMode = ref(false)
  const editingRow = ref<SilenceItem | null>(null)

  const fetchData = async () => {
    loading.value = true
    pageError.value = ''
    try {
      const data = await alertsApi.listSilences({
        page: page.value,
        page_size: pageSize.value,
        is_active: filters.isActive === '' ? undefined : filters.isActive
      })
      rows.value = data.items
      total.value = data.total
      await fetchActiveSilences()
    } catch (error) {
      pageError.value = showHttpFeedback(error, t('adminSilences.loadFailed')).detail
    } finally {
      loading.value = false
    }
  }

  const fetchActiveSilences = async () => {
    try {
      const res = await alertsApi.listActiveSilences()
      activeSilences.value = res.items
    } catch {
      // 静默生效列表加载失败不阻塞主流程
      activeSilences.value = []
    }
  }

  const handleDelete = async (row: SilenceItem) => {
    deleteLoadingId.value = row.id
    try {
      await alertsApi.deleteSilence(row.id)
      ElMessage.success(t('adminSilences.deleted'))
      await fetchData()
    } catch (error) {
      showHttpFeedback(error, t('adminSilences.deleteFailed'))
    } finally {
      deleteLoadingId.value = null
    }
  }

  // ISS-073: 启用已停用的静默规则
  const handleEnable = async (row: SilenceItem) => {
    enableLoadingId.value = row.id
    try {
      await alertsApi.enableSilence(row.id)
      ElMessage.success(t('adminSilences.enabled'))
      await fetchData()
    } catch (error) {
      showHttpFeedback(error, t('adminSilences.enableFailed'))
    } finally {
      enableLoadingId.value = null
    }
  }

  const openCreate = () => {
    isEditMode.value = false
    editingRow.value = null
    formVisible.value = true
  }

  // ISS-073: 打开编辑对话框，预填充当前规则数据
  const openEdit = (row: SilenceItem) => {
    isEditMode.value = true
    editingRow.value = row
    formVisible.value = true
  }

  const submitForm = async (payload: SilenceCreatePayload) => {
    formSaving.value = true
    try {
      if (isEditMode.value && editingRow.value) {
        await alertsApi.updateSilence(editingRow.value.id, payload)
        ElMessage.success(t('adminSilences.updated'))
      } else {
        await alertsApi.createSilence(payload)
        ElMessage.success(t('adminSilences.created'))
      }
      formVisible.value = false
      await fetchData()
    } catch (error) {
      showHttpFeedback(
        error,
        isEditMode.value ? t('adminSilences.updateFailed') : t('adminSilences.createFailed')
      )
    } finally {
      formSaving.value = false
    }
  }

  const onPageChange = async (value: number) => {
    await queryState.setQuery({ page: value })
    fetchData()
  }

  const onPageSizeChange = async (value: number) => {
    await queryState.setQuery({ page_size: value, page: 1 })
    fetchData()
  }

  const handleSearch = async () => {
    await queryState.setQuery({
      page: 1,
      is_active: filters.isActive === '' ? undefined : String(filters.isActive)
    })
    fetchData()
  }

  const handleReset = async () => {
    filters.isActive = ''
    await queryState.setQuery({ page: 1, is_active: undefined })
    fetchData()
  }

  onMounted(fetchData)

  return {
    loading, rows, total, pageError,
    deleteLoadingId, editLoadingId, enableLoadingId,
    activeSilences,
    page, pageSize, filters,
    formVisible, formSaving, isEditMode, editingRow,
    fetchData, handleDelete, handleEnable,
    openCreate, openEdit, submitForm,
    onPageChange, onPageSizeChange, handleSearch, handleReset
  }
}

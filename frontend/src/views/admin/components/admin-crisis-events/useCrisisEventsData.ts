/**
 * AdminCrisisEvents 数据加载与状态管理 composable。
 * 从原 AdminCrisisEventsPage.vue 提取所有响应式状态、加载函数与对话框操作逻辑，
 * 表格渲染下沉至 CrisisEventsTable 子组件，对话框 UI 下沉至 *EventDialog 子组件。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { adminApi, type CrisisEventItem } from '@/api/adminApi'
import { useListQueryState } from '@/composables/useListQueryState'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { getDefaultDateRange } from './sharedCrisisEventsUtils'

export function useCrisisEventsData() {
  const { t } = useI18n()

  const queryState = useListQueryState('ce')

  const loading = ref(false)
  const rows = ref<CrisisEventItem[]>([])
  const total = ref(0)
  const pageError = ref('')
  const exporting = ref(false)

  const page = computed(() => queryState.page.value)
  const pageSize = computed(() => queryState.pageSize.value)

  const filters = reactive({
    status: '',
    dateRange: getDefaultDateRange() as string[]
  })

  const fetchData = async () => {
    loading.value = true
    pageError.value = ''
    try {
      const query: { page: number; page_size: number; status?: string; start_date?: string; end_date?: string } = {
        page: page.value,
        page_size: pageSize.value
      }
      if (filters.status) query.status = filters.status
      if (filters.dateRange && filters.dateRange.length === 2) {
        query.start_date = filters.dateRange[0]
        query.end_date = filters.dateRange[1]
      }
      const data = await adminApi.getCrisisEvents(query)
      rows.value = data.items
      total.value = data.total
    } catch (error) {
      pageError.value = showHttpFeedback(error, t('adminCrisisEvents.loadFailed')).detail
    } finally {
      loading.value = false
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
    await queryState.setQuery({ page: 1 })
    fetchData()
  }

  const handleReset = async () => {
    filters.status = ''
    filters.dateRange = getDefaultDateRange()
    await queryState.setQuery({ page: 1 })
    fetchData()
  }

  const handleExport = async () => {
    if (!filters.dateRange || filters.dateRange.length < 2) {
      ElMessage.warning(t('adminCrisisEvents.exportRangeRequired'))
      return
    }
    exporting.value = true
    try {
      // ISS-051 备注：CSV 由后端 /admin/crisis-events/export 生成并以 Blob 返回，
      // 公式注入防护与单元格转义由后端统一处理；文件名仅由日期构成，无注入风险
      const blobData = await adminApi.exportCrisisEvents(filters.dateRange[0], filters.dateRange[1])
      const blob = new Blob([blobData], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `crisis_events_${filters.dateRange[0].replace(/-/g, '')}_${filters.dateRange[1].replace(/-/g, '')}.csv`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      ElMessage.success(t('adminCrisisEvents.exportSuccess'))
    } catch (error: unknown) {
      const err = error as { response?: { status?: number } }
      if (err?.response?.status === 403) {
        ElMessage.error(t('adminCrisisEvents.exportNoPermission'))
      } else {
        ElMessage.error(showHttpFeedback(error, t('adminCrisisEvents.exportFailed')).detail)
      }
    } finally {
      exporting.value = false
    }
  }

  // ISS-072 修复：状态流转对话框逻辑
  const handleDialogVisible = ref(false)
  const escalateDialogVisible = ref(false)
  const closeDialogVisible = ref(false)
  const actionLoading = ref(false)
  const currentEvent = ref<CrisisEventItem | null>(null)

  const openHandleDialog = (row: CrisisEventItem) => {
    currentEvent.value = row
    handleDialogVisible.value = true
  }

  const openEscalateDialog = (row: CrisisEventItem) => {
    currentEvent.value = row
    escalateDialogVisible.value = true
  }

  const openCloseDialog = (row: CrisisEventItem) => {
    currentEvent.value = row
    closeDialogVisible.value = true
  }

  const submitHandle = async (payload: { action: string; note: string }) => {
    if (!currentEvent.value) return
    if (!payload.action) {
      ElMessage.warning(t('adminCrisisEvents.handleActionRequired'))
      return
    }
    actionLoading.value = true
    try {
      await adminApi.handleCrisisEvent(currentEvent.value.id, {
        action: payload.action,
        note: payload.note || null
      })
      ElMessage.success(t('adminCrisisEvents.handled'))
      handleDialogVisible.value = false
      await fetchData()
    } catch (error) {
      showHttpFeedback(error, t('adminCrisisEvents.handleFailed'))
    } finally {
      actionLoading.value = false
    }
  }

  const submitEscalate = async (payload: { reason: string }) => {
    if (!currentEvent.value) return
    if (!payload.reason.trim()) {
      ElMessage.warning(t('adminCrisisEvents.escalateReasonRequired'))
      return
    }
    actionLoading.value = true
    try {
      await adminApi.escalateCrisisEvent(currentEvent.value.id, {
        reason: payload.reason
      })
      ElMessage.success(t('adminCrisisEvents.escalated'))
      escalateDialogVisible.value = false
      await fetchData()
    } catch (error) {
      showHttpFeedback(error, t('adminCrisisEvents.escalateFailed'))
    } finally {
      actionLoading.value = false
    }
  }

  const submitClose = async (payload: { note: string }) => {
    if (!currentEvent.value) return
    actionLoading.value = true
    try {
      await adminApi.closeCrisisEvent(currentEvent.value.id, {
        note: payload.note || null
      })
      ElMessage.success(t('adminCrisisEvents.closed'))
      closeDialogVisible.value = false
      await fetchData()
    } catch (error) {
      showHttpFeedback(error, t('adminCrisisEvents.closeFailed'))
    } finally {
      actionLoading.value = false
    }
  }

  onMounted(fetchData)

  return {
    loading, rows, total, pageError, exporting,
    page, pageSize, filters,
    fetchData, onPageChange, onPageSizeChange, handleSearch, handleReset, handleExport,
    handleDialogVisible, escalateDialogVisible, closeDialogVisible,
    actionLoading, currentEvent,
    openHandleDialog, openEscalateDialog, openCloseDialog,
    submitHandle, submitEscalate, submitClose
  }
}

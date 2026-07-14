/**
 * CounselorWarnings 数据加载与状态管理 composable。
 * 从原 CounselorWarningsPage.vue 提取所有响应式状态、加载函数与行内/批量操作逻辑，
 * 表格渲染下沉至 WarningsTable 子组件，详情抽屉下沉至 WarningDetailDrawer 子组件。
 */
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { counselorApi } from '@/api/counselorApi'
import type { WarningItem } from '@/api/userTypes'
import { mockWarnings } from '@/mocks/business'
import { withMockFallback } from '@/utils/mockFallback'
import { getErrorDetail } from '@/utils/errorDetail'
import { hasPermission } from '@/config/permissions'
import { useAuthStore } from '@/stores/auth'
import { useListQueryState } from '@/composables/useListQueryState'
import { useAnalytics } from '@/composables/useAnalytics'
import { showHttpFeedback } from '@/utils/httpFeedback'
import {
  isHandled,
  isRowActionDisabled,
  type RowAction,
  type RowActionContext
} from './sharedCounselorWarningsUtils'

export function useCounselorWarningsData() {
  const { t } = useI18n()
  const auth = useAuthStore()
  // P1-5 埋点与隐私：预警处理追踪（不采集预警内容）
  const { track } = useAnalytics()
  const queryState = useListQueryState('cw')

  const loading = ref(false)
  const rows = ref<WarningItem[]>([])
  const total = ref(0)
  const pageError = ref('')

  const page = computed(() => queryState.page.value)
  const pageSize = computed(() => queryState.pageSize.value)

  const rowActionPending = ref<Record<number, RowAction | undefined>>({})
  const rowErrors = ref<Record<number, string>>({})
  const rowHighlightIds = ref<Set<number>>(new Set())
  const selectedRows = ref<WarningItem[]>([])
  const batchOperating = ref(false)
  const batchAction = ref<'handle' | 'ignore' | null>(null)
  const batchPolicy = ref<'atomic' | 'partial'>((queryState.getString('policy') as 'atomic' | 'partial') || 'atomic')
  const detailVisible = ref(false)
  const detailRow = ref<WarningItem | null>(null)

  const openDetail = (row: WarningItem) => {
    detailRow.value = row
    detailVisible.value = true
  }

  const filters = reactive({ onlyUnhandled: queryState.getString('only_unhandled', '1') !== '0' })

  const isRowActionPending = (id: number, action: RowAction) => rowActionPending.value[id] === action
  const isAnyActionPending = (id: number) => !!rowActionPending.value[id]
  const setRowActionPending = (id: number, action?: RowAction) => { rowActionPending.value = { ...rowActionPending.value, [id]: action } }

  const canBatchPermission = computed(() => hasPermission(auth.role, 'counselor.warning.batch'))
  const canHandlePermission = computed(() => hasPermission(auth.role, 'counselor.warning.handle'))
  const canIgnorePermission = computed(() => hasPermission(auth.role, 'counselor.warning.ignore'))
  // ISS-058: 升级权限复用 handle 权限
  const canEscalatePermission = computed(() => hasPermission(auth.role, 'counselor.warning.handle'))
  const canBatchOperate = computed(() => canBatchPermission.value && selectedRows.value.length > 0)

  const buildActionContext = (): RowActionContext => ({
    canHandle: canHandlePermission.value,
    canIgnore: canIgnorePermission.value,
    canEscalate: canEscalatePermission.value,
    batchOperating: batchOperating.value,
    isActionPending: isAnyActionPending
  })

  const isActionDisabled = (row: WarningItem, action: RowAction) =>
    isRowActionDisabled(row, action, buildActionContext(), t)

  const clearRowError = (id: number) => { const next = { ...rowErrors.value }; delete next[id]; rowErrors.value = next }
  const clearTransientRowState = () => {
    rowErrors.value = {}
    rowHighlightIds.value = new Set()
  }
  const setRowError = (id: number, message: string) => { rowErrors.value = { ...rowErrors.value, [id]: message } }
  // P1-D-9 修复：保存 highlight timer ID 以便卸载时清理
  const highlightTimers = new Set<ReturnType<typeof setTimeout>>()
  const highlightRowFor2s = (id: number) => {
    const next = new Set(rowHighlightIds.value); next.add(id); rowHighlightIds.value = next
    const timer = setTimeout(() => {
      const after = new Set(rowHighlightIds.value); after.delete(id); rowHighlightIds.value = after
      highlightTimers.delete(timer)
    }, 2000)
    highlightTimers.add(timer)
  }

  const onSelectionChange = (tableRows: unknown[]) => { selectedRows.value = tableRows as WarningItem[] }

  const fetchData = async () => {
    loading.value = true
    pageError.value = ''
    clearTransientRowState()
    try {
      await queryState.setQuery({ page: page.value, page_size: pageSize.value, only_unhandled: filters.onlyUnhandled ? '1' : '0', policy: batchPolicy.value })
      const data = await withMockFallback(
        () => counselorApi.getCounselorWarnings({ page: page.value, page_size: pageSize.value, only_unhandled: filters.onlyUnhandled }),
        () => mockWarnings(page.value, pageSize.value)
      )
      rows.value = data.items
      total.value = data.total
      selectedRows.value = []
      clearTransientRowState()
    } catch (error) {
      pageError.value = showHttpFeedback(error, t('counselorWarnings.loadFailed')).detail
    } finally {
      loading.value = false
    }
  }

  const handleWarning = async (row: WarningItem, action: 'handle' | 'ignore') => {
    if (isActionDisabled(row, action)) return
    // ISS-059: 执行前弹出备注输入框
    let note: string | undefined
    try {
      const result = await ElMessageBox.prompt(t('counselorWarnings.promptNote'), action === 'handle' ? t('counselorWarnings.promptTitleHandle') : t('counselorWarnings.promptTitleIgnore'), {
        inputType: 'textarea',
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel')
      })
      note = result.value || undefined
    } catch {
      return
    }
    // P1-5 埋点与隐私：记录预警处理事件（仅采集预警 ID，不采集备注内容）
    track('warning_handle', { warning_id: row.id })
    const previousStatus = row.status
    const previousIsRead = row.is_read
    const previousHandledAt = row.handled_at
    const previousHandledBy = row.handled_by
    const previousHandledNote = row.handled_note
    clearRowError(row.id)
    row.status = action === 'handle' ? 'handled' : 'ignored'
    row.is_read = true
    row.handled_note = note || null
    setRowActionPending(row.id, action)
    try {
      await counselorApi.handleCounselorWarning(row.id, action, note)
      highlightRowFor2s(row.id)
      ElMessage.success(action === 'handle' ? t('counselorWarnings.warnHandled') : t('counselorWarnings.warnIgnored'))
    } catch (error) {
      row.status = previousStatus
      row.is_read = previousIsRead
      row.handled_at = previousHandledAt
      row.handled_by = previousHandledBy
      row.handled_note = previousHandledNote
      setRowError(row.id, getErrorDetail(error, action === 'handle' ? t('counselorWarnings.errHandleFailed') : t('counselorWarnings.errIgnoreFailed')))
    } finally {
      setRowActionPending(row.id, undefined)
    }
  }

  // ISS-058: 升级预警
  const escalateWarning = async (row: WarningItem) => {
    if (isActionDisabled(row, 'escalate')) return
    let reason: string
    try {
      const result = await ElMessageBox.prompt(t('counselorWarnings.promptEscalateReason'), t('counselorWarnings.promptTitleEscalate'), {
        inputType: 'textarea',
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        inputValidator: (value: string) => !!value.trim() || t('counselorWarnings.errEscalateReasonRequired')
      })
      reason = result.value.trim()
    } catch {
      return
    }
    const previousStatus = row.status
    const previousIsRead = row.is_read
    const previousHandledAt = row.handled_at
    const previousHandledBy = row.handled_by
    const previousHandledNote = row.handled_note
    clearRowError(row.id)
    row.status = 'escalated'
    row.is_read = true
    row.handled_note = reason
    setRowActionPending(row.id, 'escalate')
    try {
      await counselorApi.escalateCounselorWarning(row.id, { reason })
      highlightRowFor2s(row.id)
      ElMessage.success(t('counselorWarnings.warnEscalated'))
    } catch (error) {
      row.status = previousStatus
      row.is_read = previousIsRead
      row.handled_at = previousHandledAt
      row.handled_by = previousHandledBy
      row.handled_note = previousHandledNote
      setRowError(row.id, getErrorDetail(error, t('counselorWarnings.errEscalateFailed')))
    } finally {
      setRowActionPending(row.id, undefined)
    }
  }

  const handleBatch = async (action: 'handle' | 'ignore') => {
    if (!selectedRows.value.length || batchOperating.value) return
    const validTargets = selectedRows.value.filter((row) => !isHandled(row) && !isAnyActionPending(row.id))
    if (!validTargets.length) return ElMessage.warning(t('counselorWarnings.warnNoSelection'))
    try { await ElMessageBox.confirm(action === 'handle' ? t('counselorWarnings.batchConfirmHandle', { count: validTargets.length }) : t('counselorWarnings.batchConfirmIgnore', { count: validTargets.length }), t('counselorWarnings.batchConfirmTitle'), { type: 'warning' }) } catch { return }
    batchOperating.value = true
    batchAction.value = action
    const snapshot = validTargets.map((row) => ({ row, prevStatus: row.status, prevIsRead: row.is_read, prevHandledAt: row.handled_at, prevHandledBy: row.handled_by, prevHandledNote: row.handled_note }))
    snapshot.forEach(({ row }) => { clearRowError(row.id); row.status = action === 'handle' ? 'handled' : 'ignored'; row.is_read = true; row.handled_at = new Date().toISOString(); row.handled_by = undefined; row.handled_note = action === 'handle' ? t('counselorWarnings.batchHandleNote') : t('counselorWarnings.batchIgnoreNote'); setRowActionPending(row.id, action) })

    if (batchPolicy.value === 'atomic') {
      try {
        await Promise.all(snapshot.map(({ row }) => counselorApi.handleCounselorWarning(row.id, action)))
        snapshot.forEach(({ row }) => highlightRowFor2s(row.id))
        ElMessage.success(t('counselorWarnings.batchAtomicSuccess', { count: snapshot.length }))
      } catch (error) {
        const detail = getErrorDetail(error, action === 'handle' ? t('counselorWarnings.batchAtomicFailedHandle') : t('counselorWarnings.batchAtomicFailedIgnore'))
        snapshot.forEach(({ row, prevStatus, prevIsRead, prevHandledAt, prevHandledBy, prevHandledNote }) => { row.status = prevStatus; row.is_read = prevIsRead; row.handled_at = prevHandledAt; row.handled_by = prevHandledBy; row.handled_note = prevHandledNote; setRowError(row.id, detail) })
        ElMessage.warning(detail)
      }
    } else {
      let successCount = 0
      let failCount = 0
      const results = await Promise.allSettled(snapshot.map(({ row }) => counselorApi.handleCounselorWarning(row.id, action)))
      results.forEach((result, idx) => {
        if (result.status === 'fulfilled') {
          successCount++
          highlightRowFor2s(snapshot[idx].row.id)
        } else {
          failCount++
          const { row, prevStatus, prevIsRead, prevHandledAt, prevHandledBy, prevHandledNote } = snapshot[idx]
          row.status = prevStatus; row.is_read = prevIsRead; row.handled_at = prevHandledAt; row.handled_by = prevHandledBy; row.handled_note = prevHandledNote
          setRowError(row.id, getErrorDetail(result.reason, t('counselorWarnings.batchPartialFailure')))
        }
      })
      ElMessage.success(t('counselorWarnings.batchPartialSummary', { success: successCount, failPart: failCount > 0 ? t('counselorWarnings.batchPartialFailPart', { count: failCount }) : '' }))
    }

    snapshot.forEach(({ row }) => setRowActionPending(row.id, undefined))
    batchOperating.value = false
    batchAction.value = null
    selectedRows.value = []
  }

  const onPageChange = async (value: number) => { await queryState.setQuery({ page: value }); fetchData() }
  const onPageSizeChange = async (value: number) => { await queryState.setQuery({ page_size: value, page: 1 }); fetchData() }
  const handleReset = async () => { filters.onlyUnhandled = true; batchPolicy.value = 'atomic'; clearTransientRowState(); await queryState.setQuery({ page: 1, only_unhandled: '1', policy: 'atomic' }); fetchData() }

  onMounted(fetchData)

  // P1-D-9 修复：组件卸载时清理所有 highlight timer
  onBeforeUnmount(() => {
    highlightTimers.forEach((timer) => clearTimeout(timer))
    highlightTimers.clear()
  })

  return {
    loading, rows, total, pageError,
    page, pageSize, filters,
    rowActionPending, rowErrors, rowHighlightIds,
    batchPolicy, batchOperating, batchAction,
    detailVisible, detailRow,
    canBatchPermission, canHandlePermission, canIgnorePermission, canEscalatePermission, canBatchOperate,
    fetchData, handleWarning, escalateWarning, handleBatch,
    onPageChange, onPageSizeChange, handleReset,
    openDetail, onSelectionChange
  }
}

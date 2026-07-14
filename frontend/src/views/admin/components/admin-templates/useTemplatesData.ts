/**
 * AdminTemplates 数据加载与状态管理 composable。
 * 从原 AdminTemplatesPage.vue 提取所有响应式状态、加载函数与对话框操作逻辑，
 * 表格渲染下沉至 TemplatesTable 子组件，对话框 UI 下沉至 TemplatePreviewDialog / TemplateFormDialog 子组件。
 */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi, type TemplateItem } from '@/api/adminApi'
import { showHttpFeedback } from '@/utils/httpFeedback'
import type { TemplateStatus, TemplateUpsertPayload } from './sharedTemplatesUtils'

export function useTemplatesData() {
  const { t } = useI18n()

  const rows = ref<TemplateItem[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(10)
  const loading = ref(false)
  const pageError = ref('')

  // 表单对话框状态
  const formVisible = ref(false)
  const formSaving = ref(false)
  const isEditMode = ref(false)
  const editingRow = ref<TemplateItem | null>(null)

  // 预览对话框状态
  const previewVisible = ref(false)
  const previewRow = ref<TemplateItem | null>(null)

  const loadData = async () => {
    loading.value = true
    pageError.value = ''
    try {
      const data = await adminApi.listAdminTemplates({ page: page.value, page_size: pageSize.value })
      rows.value = data.items.map((item) => ({
        ...item,
        task_list: (item.task_list ?? []) as TemplateItem['task_list'],
      }))
      total.value = data.total
    } catch (error) {
      pageError.value = showHttpFeedback(error, t('adminTemplates.loadFailed')).detail
    } finally {
      loading.value = false
    }
  }

  const handlePageChange = (value: number) => {
    page.value = value
    loadData()
  }

  const openCreate = () => {
    isEditMode.value = false
    editingRow.value = null
    formVisible.value = true
  }

  const openEdit = (row: TemplateItem) => {
    isEditMode.value = true
    editingRow.value = row
    formVisible.value = true
  }

  const openPreview = (row: TemplateItem) => {
    previewRow.value = row
    previewVisible.value = true
  }

  // 状态切换
  const handleStatusChange = async (
    row: TemplateItem & { statusLoading?: boolean },
    val: TemplateStatus
  ) => {
    row.statusLoading = true
    try {
      await adminApi.upsertAdminTemplate({
        id: row.id,
        template_name: row.template_name,
        applicable_levels: row.applicable_levels,
        task_list: (row.task_list || []) as unknown as TemplateItem['task_list'],
        estimated_weeks: row.estimated_weeks,
        status: val,
      })
      ElMessage.success(val === 'active' ? t('adminTemplates.templateEnabled') : t('adminTemplates.templateDisabled'))
    } catch (error) {
      row.status = val === 'active' ? 'inactive' : 'active'
      showHttpFeedback(error, t('adminTemplates.statusUpdateFailed'))
    } finally {
      row.statusLoading = false
    }
  }

  // ISS-075: 删除模板
  // ISS-035 修复：删除操作属于不可逆销毁操作，确认框类型由 warning 调整为 error
  const handleDelete = async (row: TemplateItem) => {
    try {
      await ElMessageBox.confirm(
        t('adminTemplates.deleteConfirmText', { name: row.template_name }),
        t('adminTemplates.deleteConfirmTitle'),
        { type: 'error', confirmButtonText: t('adminTemplates.deleteConfirmBtn'), cancelButtonText: t('adminTemplates.deleteCancelBtn') }
      )
    } catch {
      return // 用户取消
    }
    try {
      await adminApi.deleteAdminTemplate(row.id)
      ElMessage.success(t('adminTemplates.deleteSuccess'))
      await loadData()
    } catch (error) {
      showHttpFeedback(error, t('adminTemplates.deleteFailed'))
    }
  }

  const submitForm = async (payload: TemplateUpsertPayload) => {
    formSaving.value = true
    try {
      await adminApi.upsertAdminTemplate(payload)
      formVisible.value = false
      await loadData()
      ElMessage.success(t('adminTemplates.saved'))
    } catch (error) {
      showHttpFeedback(error, t('adminTemplates.saveFailed'))
    } finally {
      formSaving.value = false
    }
  }

  onMounted(loadData)

  return {
    rows, total, page, pageSize, loading, pageError,
    formVisible, formSaving, isEditMode, editingRow,
    previewVisible, previewRow,
    loadData, handlePageChange,
    openCreate, openEdit, openPreview,
    handleStatusChange, handleDelete, submitForm,
  }
}

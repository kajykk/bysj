<template>
  <el-card class="section-card">
    <template #header>
      <span class="card-title">{{ t('userSettings.fileUpload.title') }}</span>
    </template>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="upload-alert"
    >
      {{ t('userSettings.fileUpload.description') }}
    </el-alert>

    <el-form
      label-width="90px"
      class="upload-form"
      @submit.prevent
    >
      <el-form-item :label="t('userSettings.fileUpload.categoryLabel')">
        <el-select
          v-model="category"
          class="full-width"
        >
          <el-option
            :label="t('userSettings.fileUpload.categoryAll')"
            value=""
          />
          <el-option
            :label="t('userSettings.fileUpload.categoryImage')"
            value="image"
          />
          <el-option
            :label="t('userSettings.fileUpload.categoryAudio')"
            value="audio"
          />
          <el-option
            :label="t('userSettings.fileUpload.categoryDocument')"
            value="document"
          />
        </el-select>
      </el-form-item>

      <el-form-item :label="t('userSettings.fileUpload.filesLabel')">
        <el-upload
          v-model:file-list="fileList"
          :auto-upload="false"
          :accept="acceptAttr"
          multiple
          :limit="MAX_FILES"
          :on-exceed="handleExceed"
          drag
          class="upload-dragger"
        >
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div class="upload-hint">{{ t('userSettings.fileUpload.dropHint') }}</div>
        </el-upload>
      </el-form-item>
    </el-form>

    <div class="upload-actions">
      <el-button
        :disabled="fileList.length === 0 || uploading"
        @click="clearFiles"
      >
        {{ t('userSettings.fileUpload.clearBtn') }}
      </el-button>
      <el-button
        type="primary"
        :loading="uploading"
        :disabled="fileList.length === 0"
        @click="handleUpload"
      >
        {{ fileList.length > 1 ? t('userSettings.fileUpload.batchBtn') : t('userSettings.fileUpload.uploadBtn') }}
      </el-button>
    </div>

    <Transition name="fade-slide">
      <div
        v-if="results.length > 0"
        class="upload-results"
      >
        <el-divider />
        <div class="result-summary">
          {{ t('userSettings.fileUpload.resultSummary', { success: successCount, fail: failCount }) }}
        </div>
        <el-table
          :data="results"
          size="small"
        >
          <el-table-column
            prop="originalName"
            :label="t('userSettings.fileUpload.resultFile')"
            min-width="140"
            show-overflow-tooltip
          />
          <el-table-column
            :label="t('userSettings.fileUpload.resultStatus')"
            width="90"
          >
            <template #default="{ row }">
              <el-tag
                :type="row.ok ? 'success' : 'danger'"
                size="small"
              >
                {{ row.ok ? t('userSettings.fileUpload.statusSuccess') : t('userSettings.fileUpload.statusFailed') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="detail"
            :label="t('userSettings.fileUpload.resultDetail')"
            min-width="160"
            show-overflow-tooltip
          />
        </el-table>
      </div>
    </Transition>
  </el-card>
</template>

<script setup lang="ts">
defineOptions({ name: 'FileUploadCard' })
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, type UploadFile, type UploadRawFile } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { userApi } from '@/api/userApi'
import type { UploadBatchItem } from '@/api/userFileApi'
import { normalizeHttpError } from '@/utils/errorPolicy'

const { t } = useI18n()

// 与后端 user_upload.py 的约束保持一致（MAX_FILE_SIZE / batch 上限），前端预检减少无谓 4xx 往返
const MAX_FILE_SIZE = 20 * 1024 * 1024
const MAX_FILES = 10

const category = ref('')
const fileList = ref<UploadFile[]>([])
const uploading = ref(false)

// AUDIT-2026-10-01（决策三 P6）：批量上传结果（后端单文件失败只影响该项，
// 带 error 字段，因此逐项展示而不是只看 failed 计数——后端响应模型该字段恒为 null）
interface UploadResultRow {
  originalName: string
  ok: boolean
  detail: string
}
const results = ref<UploadResultRow[]>([])
const successCount = computed(() => results.value.filter(r => r.ok).length)
const failCount = computed(() => results.value.length - successCount.value)

// 与后端 ALLOWED_EXTENSIONS 对齐的 accept 提示；选「全部」时不限制
const ACCEPT_MAP: Record<string, string> = {
  image: '.jpg,.jpeg,.png,.gif,.webp',
  audio: '.mp3,.wav,.ogg,.m4a,.aac',
  document: '.pdf,.txt,.csv'
}
const acceptAttr = computed(() => ACCEPT_MAP[category.value] ?? '')

const handleExceed = () => {
  ElMessage.warning(t('userSettings.fileUpload.overLimit', { max: MAX_FILES }))
}

const clearFiles = () => {
  fileList.value = []
  results.value = []
}

const formatSize = (size: number) => {
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

/** 组装 multipart 表单：后端单文件接口字段名为 file，批量接口为 files */
const buildFormData = (file: UploadRawFile, fieldName: string) => {
  const formData = new FormData()
  formData.append(fieldName, file, file.name)
  return formData
}

const handleUpload = async () => {
  if (fileList.value.length === 0) return
  uploading.value = true
  results.value = []
  const rows: UploadResultRow[] = []

  try {
    // 前端预检：超过 20MB 的文件直接标记跳过，不发请求
    const rawFiles = fileList.value
      .map(f => f.raw)
      .filter((f): f is UploadRawFile => !!f)
    const oversized = rawFiles.filter(f => f.size > MAX_FILE_SIZE)
    const acceptable = rawFiles.filter(f => f.size <= MAX_FILE_SIZE)
    for (const f of oversized) {
      rows.push({ originalName: f.name, ok: false, detail: t('userSettings.fileUpload.tooLarge') })
    }

    if (acceptable.length === 1) {
      // 单文件走 POST /user/upload（审计日志 action_type 与批量接口不同）
      try {
        const saved = await userApi.uploadFile(buildFormData(acceptable[0], 'file'), category.value || undefined)
        rows.push({
          originalName: saved.original_name || acceptable[0].name,
          ok: true,
          detail: `${saved.filename} · ${formatSize(saved.size)}`
        })
      } catch (error) {
        rows.push({
          originalName: acceptable[0].name,
          ok: false,
          detail: normalizeHttpError(error, t('userSettings.fileUpload.uploadFailed')).detail
        })
      }
    } else if (acceptable.length > 1) {
      const formData = new FormData()
      for (const f of acceptable) {
        formData.append('files', f, f.name)
      }
      try {
        const batch = await userApi.uploadFiles(formData, category.value || undefined)
        const items: UploadBatchItem[] = batch.items ?? []
        for (const item of items) {
          rows.push({
            originalName: item.original_name || item.filename || '-',
            ok: !item.error,
            detail: item.error ?? `${item.filename ?? ''} · ${formatSize(item.size ?? 0)}`.trim()
          })
        }
      } catch (error) {
        // 整批失败（如 400 超 10 个 / 413）：逐文件标记失败，保证每行都有归属
        for (const f of acceptable) {
          rows.push({
            originalName: f.name,
            ok: false,
            detail: normalizeHttpError(error, t('userSettings.fileUpload.uploadFailed')).detail
          })
        }
      }
    }

    results.value = rows
    if (failCount.value === 0 && successCount.value > 0) {
      ElMessage.success(t('userSettings.fileUpload.uploadSuccess', { count: successCount.value }))
    } else if (failCount.value > 0) {
      ElMessage.warning(t('userSettings.fileUpload.uploadPartial', { success: successCount.value, fail: failCount.value }))
    }
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.section-card {
  margin-top: var(--spacing-lg);
}

.upload-alert {
  margin-bottom: var(--spacing-md);
}

.upload-form {
  margin-top: var(--spacing-sm);
}

.full-width {
  width: 100%;
}

.upload-dragger {
  width: 100%;
}

.upload-icon {
  font-size: 40px;
  color: var(--el-text-color-placeholder);
  margin-bottom: 8px;
}

.upload-hint {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.upload-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}

.upload-results {
  margin-top: var(--spacing-sm);
}

.result-summary {
  font-size: var(--font-size-small);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-sm);
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>

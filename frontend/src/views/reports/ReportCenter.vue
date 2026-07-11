<template>
  <div class="report-center">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>{{ $t('report.title') }}</h1>
    </div>

    <!-- 报告生成区域 -->
    <el-card class="generate-section">
      <template #header>
        <span>{{ $t('report.generateReport') }}</span>
      </template>

      <el-form
        :model="form"
        label-width="120px"
        class="report-form"
      >
        <el-form-item :label="$t('report.reportType')">
          <el-radio-group v-model="form.reportType">
            <el-radio-button label="userRisk">
              {{ $t('report.reportTypes.userRisk') }}
            </el-radio-button>
            <el-radio-button label="counselor">
              {{ $t('report.reportTypes.counselor') }}
            </el-radio-button>
            <el-radio-button label="admin">
              {{ $t('report.reportTypes.admin') }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="时间范围">
          <el-date-picker
            v-model="form.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :icon="Document"
            :loading="generatingPdf"
            @click="generatePdf"
          >
            {{ $t('report.downloadPdf') }}
          </el-button>
          <el-button
            :icon="Download"
            :loading="generatingExcel"
            @click="generateExcel"
          >
            {{ $t('report.downloadExcel') }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 导出历史 -->
    <el-card class="history-section">
      <template #header>
        <div class="card-header">
          <span>{{ $t('report.exportHistory') }}</span>
          <el-button
            :icon="Refresh"
            size="small"
            @click="refreshHistory"
          >
            刷新
          </el-button>
        </div>
      </template>

      <el-skeleton
        v-if="loading"
        :rows="5"
        animated
      />

      <el-table
        v-else
        :data="exportHistory"
        style="width: 100%"
      >
        <el-table-column
          prop="id"
          label="ID"
          width="80"
        />
        <el-table-column
          prop="reportType"
          :label="$t('report.reportType')"
          width="150"
        >
          <template #default="{ row }">
            {{ $t(`report.reportTypes.${row.reportType}`) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="format"
          label="格式"
          width="100"
        >
          <template #default="{ row }">
            <el-tag :type="row.format === 'pdf' ? 'danger' : 'success'">
              {{ row.format.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="status"
          :label="$t('report.exportStatus')"
          width="120"
        >
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ $t(`report.exportStatus.${row.status}`) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="createdAt"
          :label="$t('report.createdAt')"
          width="180"
        >
          <template #default="{ row }">
            {{ formatDate(row.createdAt) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="completedAt"
          :label="$t('report.completedAt')"
          width="180"
        >
          <template #default="{ row }">
            {{ row.completedAt ? formatDate(row.completedAt) : '-' }}
          </template>
        </el-table-column>
        <el-table-column
          prop="fileSize"
          :label="$t('report.fileSize')"
          width="120"
        >
          <template #default="{ row }">
            {{ row.fileSize ? formatFileSize(row.fileSize) : '-' }}
          </template>
        </el-table-column>
        <el-table-column
          :label="$t('report.actions')"
          width="150"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'completed' && row.downloadUrl"
              type="primary"
              size="small"
              :icon="Download"
              @click="downloadFile(row.downloadUrl, row.fileName)"
            >
              下载
            </el-button>
            <el-button
              v-if="row.status === 'failed'"
              size="small"
              @click="retryExport(row.id)"
            >
              重试
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next"
          :page-sizes="[10, 20, 50]"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Document, Download, Refresh } from '@element-plus/icons-vue'

interface ExportRecord {
  id: number
  reportType: 'userRisk' | 'counselor' | 'admin'
  format: 'pdf' | 'excel'
  status: 'pending' | 'processing' | 'completed' | 'failed'
  createdAt: string
  completedAt?: string
  fileSize?: number
  downloadUrl?: string
  fileName?: string
}

// 表单状态
const form = reactive({
  reportType: 'userRisk' as 'userRisk' | 'counselor' | 'admin',
  dateRange: [] as string[],
})

// 加载状态
const loading = ref(false)
const generatingPdf = ref(false)
const generatingExcel = ref(false)

// 导出历史
const exportHistory = ref<ExportRecord[]>([])

// 分页
const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0,
})

// 格式化日期
const formatDate = (dateStr: string): string => {
  return new Date(dateStr).toLocaleString('zh-CN')
}

// 格式化文件大小
const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`
}

// 获取状态类型
const getStatusType = (status: string): 'info' | 'warning' | 'success' | 'danger' | 'primary' => {
  const map: Record<string, 'info' | 'warning' | 'success' | 'danger' | 'primary'> = {
    pending: 'info',
    processing: 'warning',
    completed: 'success',
    failed: 'danger',
  }
  return map[status] || 'info'
}

// 生成 PDF
const generatePdf = async () => {
  generatingPdf.value = true
  try {
    // 模拟 API 调用
    await new Promise((resolve) => setTimeout(resolve, 1500))

    // 添加到历史记录
    const newRecord: ExportRecord = {
      id: Date.now(),
      reportType: form.reportType,
      format: 'pdf',
      status: 'completed',
      createdAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
      fileSize: 1024 * 1024 * 2.5,
      downloadUrl: '#',
      fileName: `report_${form.reportType}_${new Date().toISOString().split('T')[0]}.pdf`,
    }
    exportHistory.value.unshift(newRecord)
  } finally {
    generatingPdf.value = false
  }
}

// 生成 Excel
const generateExcel = async () => {
  generatingExcel.value = true
  try {
    // 模拟 API 调用
    await new Promise((resolve) => setTimeout(resolve, 2000))

    // 添加到历史记录
    const newRecord: ExportRecord = {
      id: Date.now(),
      reportType: form.reportType,
      format: 'excel',
      status: 'completed',
      createdAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
      fileSize: 1024 * 512,
      downloadUrl: '#',
      fileName: `report_${form.reportType}_${new Date().toISOString().split('T')[0]}.xlsx`,
    }
    exportHistory.value.unshift(newRecord)
  } finally {
    generatingExcel.value = false
  }
}

// 下载文件
const downloadFile = (url: string, fileName?: string) => {
  const link = document.createElement('a')
  link.href = url
  if (fileName) {
    link.download = fileName
  }
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

// 重试导出
const retryExport = async (id: number) => {
  const record = exportHistory.value.find((r) => r.id === id)
  if (!record) return

  record.status = 'processing'
  try {
    await new Promise((resolve) => setTimeout(resolve, 1500))
    record.status = 'completed'
    record.completedAt = new Date().toISOString()
  } catch {
    record.status = 'failed'
  }
}

// 刷新历史
const refreshHistory = async () => {
  loading.value = true
  try {
    await new Promise((resolve) => setTimeout(resolve, 500))
    // 模拟数据已在 onMounted 中生成
  } finally {
    loading.value = false
  }
}

// 分页处理
const handlePageChange = (page: number) => {
  pagination.page = page
}

const handleSizeChange = (size: number) => {
  pagination.pageSize = size
  pagination.page = 1
}

// 生成模拟数据
const generateMockData = () => {
  const types: ('userRisk' | 'counselor' | 'admin')[] = ['userRisk', 'counselor', 'admin']
  const formats: ('pdf' | 'excel')[] = ['pdf', 'excel']
  const statuses: ('pending' | 'processing' | 'completed' | 'failed')[] = ['completed', 'completed', 'completed', 'failed', 'processing']

  exportHistory.value = Array.from({ length: 15 }, (_, i) => {
    const createdAt = new Date(Date.now() - i * 3600 * 1000)
    const status = statuses[Math.floor(Math.random() * statuses.length)]
    return {
      id: i + 1,
      reportType: types[Math.floor(Math.random() * types.length)],
      format: formats[Math.floor(Math.random() * formats.length)],
      status,
      createdAt: createdAt.toISOString(),
      completedAt: status === 'completed' ? new Date(createdAt.getTime() + 30000).toISOString() : undefined,
      fileSize: status === 'completed' ? Math.floor(Math.random() * 1024 * 1024 * 5) : undefined,
      downloadUrl: status === 'completed' ? '#' : undefined,
      fileName: `report_${i + 1}.pdf`,
    }
  })

  pagination.total = exportHistory.value.length
}

onMounted(() => {
  generateMockData()
})
</script>

<style scoped>
.report-center {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0;
  font-size: var(--font-size-display);
  font-weight: var(--font-weight-bold);
  letter-spacing: var(--letter-spacing-tight);
  line-height: var(--line-height-tight);
  color: var(--text-primary);
}

.generate-section {
  margin-bottom: 20px;
}

.report-form {
  max-width: 600px;
}

.history-section {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pagination-wrap {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 768px) {
  .report-form {
    max-width: 100%;
  }
}
</style>

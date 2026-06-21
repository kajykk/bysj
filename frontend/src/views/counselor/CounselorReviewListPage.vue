<template>
  <div class="review-list-page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span class="card-title">复核任务管理</span>
          <el-button type="primary" @click="loadReviews">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <!-- 筛选栏 -->
      <el-form :inline="true" class="filter-form">
        <el-form-item label="状态">
          <el-select v-model="filterStatus" placeholder="全部状态" clearable>
            <el-option label="待处理" value="pending" />
            <el-option label="处理中" value="in_review" />
            <el-option label="已处理" value="resolved" />
            <el-option label="已升级" value="escalated" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="filterPriority" placeholder="全部优先级" clearable>
            <el-option label="普通" value="normal_review" />
            <el-option label="高风险" value="high_risk_review" />
            <el-option label="危机" value="crisis_review" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadReviews">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>

      <!-- 统计卡片 -->
      <el-row :gutter="16" class="stats-row">
        <el-col :span="6">
          <el-statistic title="待处理" :value="stats.pending" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="处理中" :value="stats.in_review" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="已处理" :value="stats.resolved" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="危机事件" :value="stats.crisis_count">
            <template #suffix>
              <el-icon color="#f56c6c"><Warning /></el-icon>
            </template>
          </el-statistic>
        </el-col>
      </el-row>

      <!-- 任务列表 -->
      <el-table
        v-loading="loading"
        :data="reviews"
        style="width: 100%; margin-top: 16px"
        @row-click="handleRowClick"
      >
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="user_id" label="用户ID" width="80" />
        <el-table-column label="风险等级" width="100">
          <template #default="{ row }">
            <el-tag :type="getRiskLevelType(row.risk_level)">
              {{ getRiskLevelLabel(row.risk_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="优先级" width="100">
          <template #default="{ row }">
            <el-tag
              :type="getPriorityType(row.priority)"
              effect="dark"
            >
              {{ getPriorityLabel(row.priority) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="危机覆盖" width="100">
          <template #default="{ row }">
            <el-tag
              v-if="row.crisis_override"
              type="danger"
              effect="dark"
            >
              是
            </el-tag>
            <span v-else>否</span>
          </template>
        </el-table-column>
        <el-table-column label="复核原因" min-width="200">
          <template #default="{ row }">
            <el-tag
              v-for="trigger in row.review_triggers"
              :key="trigger"
              type="warning"
              size="small"
              style="margin-right: 4px; margin-bottom: 4px"
            >
              {{ trigger }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              @click.stop="handleRowClick(row)"
            >
              查看
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        style="margin-top: 16px; justify-content: flex-end"
        @change="loadReviews"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Warning } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
// 使用项目封装的 request 实例，确保 Authorization 注入、401 刷新与统一错误处理
import request from '@/api/request'
// P2-A 修复：复用 formatUtils 的 formatDate，避免本地重复定义
import { formatDate } from '@/utils/formatUtils'

// P1-E 修复：移除 any 类型，定义明确的接口类型
interface ReviewItem {
  id: number
  user_id: number
  risk_level: number
  priority: string
  status: string
  crisis_override: boolean
  review_triggers: string[]
  created_at: string
}

interface ReviewListParams {
  page: number
  page_size: number
  status?: string
  priority?: string
}

const router = useRouter()

const loading = ref(false)
const reviews = ref<ReviewItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filterStatus = ref('')
const filterPriority = ref('')

const stats = ref({
  pending: 0,
  in_review: 0,
  resolved: 0,
  crisis_count: 0,
})

const loadReviews = async () => {
  loading.value = true
  try {
    // P1-E 修复：移除 any 类型，使用明确的参数类型
    const params: ReviewListParams = {
      page: page.value,
      page_size: pageSize.value,
    }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterPriority.value) params.priority = filterPriority.value

    const response = await request.get('/reviews', { params })
    const data = response.data.data
    reviews.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error('加载复核任务失败')
  } finally {
    loading.value = false
  }
}

const loadStats = async () => {
  try {
    const response = await request.get('/reviews/stats')
    stats.value = response.data.data
  } catch (error) {
    console.error('加载统计失败', error)
  }
}

const resetFilter = () => {
  filterStatus.value = ''
  filterPriority.value = ''
  page.value = 1
  loadReviews()
}

// P1-E 修复：移除 any 类型，使用明确的 ReviewItem 类型
const handleRowClick = (row: ReviewItem) => {
  router.push(`/counselor/reviews/${row.id}`)
}

type ElTagType = 'primary' | 'success' | 'warning' | 'danger' | 'info'

const getRiskLevelType = (level: number): ElTagType => {
  const types: ElTagType[] = ['success', 'success', 'warning', 'danger', 'danger']
  return types[level] || 'info'
}

const getRiskLevelLabel = (level: number) => {
  const labels = ['无', '轻度', '中度', '较高', '严重']
  return labels[level] || '未知'
}

const getPriorityType = (priority: string): ElTagType => {
  const types: Record<string, ElTagType> = {
    normal_review: 'info',
    high_risk_review: 'warning',
    crisis_review: 'danger',
  }
  return types[priority] || 'info'
}

const getPriorityLabel = (priority: string) => {
  const labels: Record<string, string> = {
    normal_review: '普通',
    high_risk_review: '高风险',
    crisis_review: '危机',
  }
  return labels[priority] || '未知'
}

const getStatusType = (status: string): ElTagType => {
  const types: Record<string, ElTagType> = {
    pending: 'warning',
    in_review: 'primary',
    resolved: 'success',
    escalated: 'danger',
  }
  return types[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    pending: '待处理',
    in_review: '处理中',
    resolved: '已处理',
    escalated: '已升级',
  }
  return labels[status] || '未知'
}

onMounted(() => {
  loadReviews()
  loadStats()
})
</script>

<style scoped>
.review-list-page {
  padding: 16px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
}

.filter-form {
  margin-bottom: 16px;
}

.stats-row {
  margin-bottom: 16px;
}

:deep(.el-table__row) {
  cursor: pointer;
}

:deep(.el-table__row:hover) {
  background-color: #f5f7fa;
}
</style>

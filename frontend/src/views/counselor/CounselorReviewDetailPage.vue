<template>
  <div class="review-detail-page">
    <el-page-header @back="goBack" title="复核详情" />

    <el-card v-if="review" style="margin-top: 16px">
      <!-- 危机警告横幅 -->
      <el-alert
        v-if="review.crisis_override"
        title="危机事件"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #default>
          <strong>该用户触发了危机表达覆盖，请立即关注并处理。</strong>
        </template>
      </el-alert>

      <!-- 用户信息 -->
      <el-descriptions title="用户信息" :column="2" border>
        <el-descriptions-item label="用户ID">{{ review.user_id }}</el-descriptions-item>
        <el-descriptions-item label="复核ID">{{ review.id }}</el-descriptions-item>
      </el-descriptions>

      <!-- 模型预测结果 -->
      <el-descriptions title="模型预测结果" :column="2" border style="margin-top: 16px">
        <el-descriptions-item label="风险分数">
          <el-progress
            :percentage="review.risk_score"
            :color="getScoreColor(review.risk_score)"
            :stroke-width="16"
          />
        </el-descriptions-item>
        <el-descriptions-item label="风险等级">
          <el-tag :type="getRiskLevelType(review.risk_level)" size="large">
            {{ getRiskLevelLabel(review.risk_level) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="优先级">
          <el-tag :type="getPriorityType(review.priority)" effect="dark">
            {{ getPriorityLabel(review.priority) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(review.status)">
            {{ getStatusLabel(review.status) }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <!-- 触发原因 -->
      <el-descriptions title="触发原因" :column="1" border style="margin-top: 16px">
        <el-descriptions-item label="复核原因">
          <el-tag
            v-for="trigger in review.review_triggers"
            :key="trigger"
            type="warning"
            style="margin-right: 8px"
          >
            {{ trigger }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="危机覆盖">
          {{ review.crisis_override ? '是' : '否' }}
        </el-descriptions-item>
      </el-descriptions>

      <!-- 处理操作 -->
      <div v-if="review.status === 'pending' || review.status === 'in_review'" class="actions" style="margin-top: 24px">
        <el-divider>处理操作</el-divider>

        <el-form :model="form" label-width="100px">
          <el-form-item label="处理备注">
            <el-input
              v-model="form.note"
              type="textarea"
              :rows="4"
              placeholder="请输入处理备注..."
            />
          </el-form-item>

          <el-form-item>
            <el-button type="success" @click="handleResolve">
              <el-icon><Check /></el-icon>
              标记已处理
            </el-button>
            <el-button type="danger" @click="handleEscalate">
              <el-icon><Top /></el-icon>
              升级危机事件
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 处理结果 -->
      <div v-else class="resolution" style="margin-top: 24px">
        <el-divider>处理结果</el-divider>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="处理人">{{ review.resolved_by }}</el-descriptions-item>
          <el-descriptions-item label="处理备注">{{ review.resolution_note }}</el-descriptions-item>
          <el-descriptions-item label="处理时间">{{ formatDate(review.resolved_at) }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <el-skeleton v-else :rows="10" animated />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Check, Top } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
// 使用项目封装的 request 实例，确保 Authorization 注入、401 刷新与统一错误处理
import request from '@/api/request'

// P1-E 修复：移除 any 类型，定义明确的接口类型
interface ReviewDetail {
  id: number
  user_id: number
  risk_score: number
  risk_level: number
  priority: string
  status: string
  crisis_override: boolean
  review_triggers: string[]
  resolved_by?: string | null
  resolution_note?: string | null
  resolved_at?: string | null
}

const route = useRoute()
const router = useRouter()

const review = ref<ReviewDetail | null>(null)
const form = ref({
  note: '',
})

const loadReview = async () => {
  const id = route.params.id
  try {
    const response = await request.get(`/reviews/${id}`)
    review.value = response.data.data
  } catch (error) {
    ElMessage.error('加载复核详情失败')
  }
}

const goBack = () => {
  router.push('/counselor/reviews')
}

// P1-E 修复：移除 any 类型，使用 unknown 并进行类型守卫
const handleResolve = async () => {
  try {
    await ElMessageBox.confirm('确认标记该复核任务为已处理？', '确认', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })

    const id = route.params.id
    await request.post(`/reviews/${id}/resolve`, null, {
      params: { resolution_note: form.value.note || '已处理' },
    })

    ElMessage.success('已标记为处理完成')
    loadReview()
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error('处理失败')
    }
  }
}

const handleEscalate = async () => {
  try {
    await ElMessageBox.confirm('确认升级该危机事件？', '确认', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'error',
    })

    const id = route.params.id
    await request.post(`/reviews/${id}/escalate`, null, {
      params: { reason: form.value.note || '需要升级处理' },
    })

    ElMessage.success('已升级危机事件')
    loadReview()
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error('升级失败')
    }
  }
}

const getScoreColor = (score: number) => {
  if (score >= 80) return '#f56c6c'
  if (score >= 60) return '#e6a23c'
  if (score >= 40) return '#409eff'
  return '#67c23a'
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

const formatDate = (date: string) => {
  return date ? new Date(date).toLocaleString('zh-CN') : '-'
}

onMounted(() => {
  loadReview()
})
</script>

<style scoped>
.review-detail-page {
  padding: 16px;
}

.actions {
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}

.resolution {
  padding: 16px;
  background: #f0f9ff;
  border-radius: 8px;
}
</style>

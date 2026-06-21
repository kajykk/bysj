<template>
  <el-card>
    <template #header>
      评估记录详情
    </template>

    <StatefulContainer
      :loading="loading"
      :empty="!loading && !record"
      :error-message="pageError"
      empty-text="未找到记录"
      @retry="fetchDetail"
    >
      <el-descriptions
        v-if="record"
        :column="1"
        border
      >
        <el-descriptions-item label="记录ID">
          {{ record.id }}
        </el-descriptions-item>
        <el-descriptions-item label="评估类型">
          {{ assessmentTypeLabel(record.assessment_type) }}
        </el-descriptions-item>
        <el-descriptions-item label="得分">
          {{ record.score ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="风险等级">
          {{ record.risk_level ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="时间">
          {{ record.created_at ? formatDateTime(record.created_at) : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="摘要">
          {{ record.summary ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="详情">
          {{ record.detail ?? '-' }}
        </el-descriptions-item>
      </el-descriptions>

      <div
        v-if="record"
        class="json-box"
      >
        <div class="json-box__title">
          原始数据
        </div>
        <pre>{{ JSON.stringify(record, null, 2) }}</pre>
      </div>

      <div class="footer">
        <el-button @click="goBack">
          返回列表
        </el-button>
      </div>
    </StatefulContainer>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { userApi, type AssessmentRecordItem } from '@/api/userApi'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import { normalizeHttpError } from '@/utils/errorPolicy'
// P2-A 修复：复用 formatUtils 的 formatDate（别名 formatDateTime 保持模板兼容），避免本地重复定义
import { formatDate as formatDateTime } from '@/utils/formatUtils'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const pageError = ref('')
const record = ref<AssessmentRecordItem | null>(null)

const recordId = computed(() => Number(route.params.id))

const assessmentTypeLabel = (value?: string) => {
  const map: Record<string, string> = { structured: '结构化', text: '文本', physiological: '生理', record: '记录' }
  return map[value || ''] || value || '-'
}

const fetchDetail = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const pageSize = 100
    let found: AssessmentRecordItem | null = null
    for (let page = 1; page <= 10; page += 1) {
      const data = await userApi.getUserAssessmentHistory({ page, page_size: pageSize })
      found = data.items.find((item) => item.id === recordId.value) || null
      if (found || data.items.length < pageSize) break
    }
    record.value = found
  } catch (error) {
    pageError.value = normalizeHttpError(error, '详情加载失败').detail
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  router.push({ path: '/user/assessments', query: route.query })
}

onMounted(fetchDetail)
</script>

<style scoped>
.footer {
  margin-top: 12px;
}

.json-box {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafafa;
}

.json-box__title {
  margin-bottom: 8px;
  font-weight: 600;
  color: #303133;
}

pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
}
</style>

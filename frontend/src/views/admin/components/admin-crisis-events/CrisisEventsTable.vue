<template>
  <PageTable
    :loading="loading"
    :data="data"
    :total="total"
    :page="page"
    :page-size="pageSize"
    @update:page="(v: number) => emit('update:page', v)"
    @update:page-size="(v: number) => emit('update:pageSize', v)"
  >
    <el-table-column
      prop="id"
      :label="t('adminCrisisEvents.colId')"
      width="70"
    />
    <el-table-column
      prop="user_id"
      :label="t('adminCrisisEvents.colUserId')"
      width="100"
    >
      <template #default="{ row }">
        {{ maskUserId(row.user_id) }}
      </template>
    </el-table-column>
    <el-table-column
      prop="trigger_source"
      :label="t('adminCrisisEvents.colTriggerSource')"
      width="100"
    >
      <template #default="{ row }">
        <el-tag
          :type="getTriggerSourceTag(row.trigger_source)"
          size="small"
        >
          {{ getTriggerSourceLabel(row.trigger_source) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column
      prop="crisis_score"
      :label="t('adminCrisisEvents.colCrisisScore')"
      width="120"
    >
      <template #default="{ row }">
        <span :style="{ color: getScoreColor(row.crisis_score), fontWeight: 'bold' }">
          {{ row.crisis_score != null ? row.crisis_score.toFixed(1) : '-' }}
        </span>
        <!-- ISS-040 修复：颜色旁附加文字标签，避免颜色作为唯一状态表达（A11Y） -->
        <el-tag
          v-if="row.crisis_score != null"
          :color="getScoreColor(row.crisis_score)"
          effect="dark"
          size="small"
          class="score-label"
          :aria-label="t('adminCrisisEvents.colCrisisScore') + ': ' + getScoreLabel(row.crisis_score)"
        >
          {{ getScoreLabel(row.crisis_score) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column
      prop="status"
      :label="t('adminCrisisEvents.colStatus')"
      width="100"
    >
      <template #default="{ row }">
        <el-tag
          :type="getStatusTag(row.status)"
          size="small"
        >
          {{ getStatusLabel(row.status) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column
      prop="crisis_keywords"
      :label="t('adminCrisisEvents.colKeywords')"
      min-width="150"
    >
      <template #default="{ row }">
        <template v-if="row.crisis_keywords && row.crisis_keywords.length">
          <el-tag
            v-for="kw in row.crisis_keywords"
            :key="kw"
            size="small"
            type="warning"
            effect="plain"
            class="keyword-tag"
          >
            {{ kw }}
          </el-tag>
        </template>
        <span
          v-else
          class="empty-cell"
        >-</span>
      </template>
    </el-table-column>
    <el-table-column
      prop="review_task_id"
      :label="t('adminCrisisEvents.colReviewTask')"
      width="90"
    >
      <template #default="{ row }">
        <template v-if="row.review_task_id">
          <el-tag
            type="primary"
            size="small"
          >
            #{{ row.review_task_id }}
          </el-tag>
        </template>
        <span
          v-else
          class="empty-cell"
        >-</span>
      </template>
    </el-table-column>
    <el-table-column
      prop="created_at"
      :label="t('adminCrisisEvents.colCreatedAt')"
      min-width="170"
    >
      <template #default="{ row }">
        {{ formatDate(row.created_at) }}
      </template>
    </el-table-column>
    <el-table-column
      prop="handled_by"
      :label="t('adminCrisisEvents.colHandledBy')"
      width="100"
    >
      <template #default="{ row }">
        {{ row.handled_by ? maskUserId(row.handled_by) : '-' }}
      </template>
    </el-table-column>
    <el-table-column
      prop="handled_action"
      :label="t('adminCrisisEvents.colHandledAction')"
      min-width="120"
    >
      <template #default="{ row }">
        {{ row.handled_action || '-' }}
      </template>
    </el-table-column>
    <el-table-column
      :label="t('adminCrisisEvents.colOperation')"
      width="200"
      fixed="right"
    >
      <template #default="{ row }">
        <el-button
          v-if="canHandle(row.status)"
          link
          type="primary"
          size="small"
          @click="emit('handle', row)"
        >
          {{ t('adminCrisisEvents.actionHandle') }}
        </el-button>
        <el-button
          v-if="canEscalate(row.status)"
          link
          type="warning"
          size="small"
          @click="emit('escalate', row)"
        >
          {{ t('adminCrisisEvents.actionEscalate') }}
        </el-button>
        <el-button
          v-if="canClose(row.status)"
          link
          type="success"
          size="small"
          @click="emit('close', row)"
        >
          {{ t('adminCrisisEvents.actionClose') }}
        </el-button>
        <span
          v-if="row.status === 'resolved'"
          class="empty-cell"
        >{{ t('adminCrisisEvents.statusClosed') }}</span>
      </template>
    </el-table-column>
  </PageTable>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import PageTable from '@/components/common/PageTable.vue'
// P2-A 修复：复用 formatUtils 的 formatDate，避免本地重复定义
import { formatDate } from '@/utils/formatUtils'
import type { CrisisEventItem } from '@/api/adminApi'
import {
  TRIGGER_SOURCE_TAG_MAP,
  TRIGGER_SOURCE_LABEL_KEYS,
  STATUS_TAG_MAP,
  STATUS_LABEL_KEYS,
  getScoreLevelKey,
  getScoreColor,
  maskUserId,
  canHandle,
  canEscalate,
  canClose
} from './sharedCrisisEventsUtils'

defineProps<{
  loading: boolean
  data: CrisisEventItem[]
  total: number
  page: number
  pageSize: number
}>()

const emit = defineEmits<{
  (e: 'update:page', value: number): void
  (e: 'update:pageSize', value: number): void
  (e: 'handle', row: CrisisEventItem): void
  (e: 'escalate', row: CrisisEventItem): void
  (e: 'close', row: CrisisEventItem): void
}>()

const { t } = useI18n()

const getTriggerSourceTag = (source: string) => TRIGGER_SOURCE_TAG_MAP[source] || 'info'

const getTriggerSourceLabel = (source: string): string => {
  const key = TRIGGER_SOURCE_LABEL_KEYS[source]
  return key ? t('adminCrisisEvents.' + key) : source
}

const getStatusTag = (status: string) => STATUS_TAG_MAP[status] || 'info'

const getStatusLabel = (status: string): string => {
  const key = STATUS_LABEL_KEYS[status]
  return key ? t('adminCrisisEvents.' + key) : status
}

const getScoreLabel = (score: number | null): string => {
  const key = getScoreLevelKey(score)
  if (!key) return '-'
  return t('adminCrisisEvents.' + key)
}
</script>

<style scoped>
.keyword-tag {
  margin-right: var(--spacing-xs);
  margin-bottom: 2px;
}

/* ISS-040 修复：危机分数风险等级标签样式 */
.score-label {
  margin-left: var(--spacing-xs);
  color: #ffffff;
  border: none;
  font-weight: 600;
}

.empty-cell {
  color: var(--text-placeholder);
}
</style>

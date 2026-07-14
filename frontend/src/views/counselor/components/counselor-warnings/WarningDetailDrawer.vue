<template>
  <el-drawer
    :model-value="visible"
    :title="t('counselorWarnings.detailTitle')"
    size="500px"
    destroy-on-close
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <div
      v-if="detailRow"
      class="detail-content"
    >
      <el-descriptions
        :column="1"
        border
      >
        <el-descriptions-item :label="t('counselorWarnings.colId')">
          {{ detailRow.id }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorWarnings.colTitle')">
          {{ detailRow.title }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorWarnings.detailColContent')">
          {{ detailRow.content }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorWarnings.colRiskLevel')">
          <el-tag
            :type="getWarningRiskLevelTagType(detailRow.risk_level)"
            size="small"
          >
            {{ getWarningRiskLevelLabel(detailRow.risk_level) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorWarnings.colStatus')">
          <el-tag
            :type="getWarningStatusTagType(detailRow.status)"
            size="small"
          >
            {{ getWarningStatusLabel(detailRow.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorWarnings.colReadStatus')">
          <el-tag
            :type="detailRow.is_read ? 'success' : 'warning'"
            size="small"
          >
            {{ detailRow.is_read ? t('warning.read') : t('warning.unread') }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorWarnings.colHandledBy')">
          {{ detailRow.handled_by || '—' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorWarnings.colHandledAt')">
          {{ formatWarningDateTime(detailRow.handled_at) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorWarnings.colCreatedAt')">
          {{ formatWarningDateTime(detailRow.created_at) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('counselorWarnings.colHandledNote')">
          {{ detailRow.handled_note || '—' }}
        </el-descriptions-item>
      </el-descriptions>
      <div class="detail-actions">
        <ActionColumn
          v-if="canHandlePermission && !isHandled(detailRow)"
          :label="t('counselorWarnings.actionHandle')"
          type="primary"
          :disabled="isActionDisabled(detailRow, 'handle')"
          :disabled-reason="getDisabledReason(detailRow, 'handle')"
          show-audit
          @action="onHandle"
        />
        <ActionColumn
          v-if="canIgnorePermission && !isHandled(detailRow)"
          :label="t('counselorWarnings.actionIgnore')"
          type="info"
          :disabled="isActionDisabled(detailRow, 'ignore')"
          :disabled-reason="getDisabledReason(detailRow, 'ignore')"
          show-audit
          @action="onIgnore"
        />
        <!-- ISS-058: 详情抽屉升级按钮 -->
        <ActionColumn
          v-if="canEscalatePermission && !isHandled(detailRow)"
          :label="t('counselorWarnings.actionEscalate')"
          type="warning"
          :disabled="isActionDisabled(detailRow, 'escalate')"
          :disabled-reason="getDisabledReason(detailRow, 'escalate')"
          show-audit
          @action="onEscalate"
        />
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import ActionColumn from '@/components/common/ActionColumn.vue'
import type { WarningItem } from '@/api/userTypes'
import { formatWarningDateTime, getWarningRiskLevelLabel, getWarningRiskLevelTagType, getWarningStatusLabel, getWarningStatusTagType } from '@/utils/warning'
import {
  isHandled,
  isRowActionDisabled,
  getRowDisabledReason,
  type RowAction,
  type RowActionContext
} from './sharedCounselorWarningsUtils'

const props = defineProps<{
  visible: boolean
  detailRow: WarningItem | null
  canHandlePermission: boolean
  canIgnorePermission: boolean
  canEscalatePermission: boolean
  batchOperating: boolean
  rowActionPending: Record<number, RowAction | undefined>
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'handle', row: WarningItem): void
  (e: 'ignore', row: WarningItem): void
  (e: 'escalate', row: WarningItem): void
}>()

const { t } = useI18n()

const isAnyActionPending = (id: number) => !!props.rowActionPending[id]

const buildActionContext = (): RowActionContext => ({
  canHandle: props.canHandlePermission,
  canIgnore: props.canIgnorePermission,
  canEscalate: props.canEscalatePermission,
  batchOperating: props.batchOperating,
  isActionPending: isAnyActionPending
})

const getDisabledReason = (row: WarningItem, action: RowAction) =>
  getRowDisabledReason(row, action, buildActionContext(), t)
const isActionDisabled = (row: WarningItem, action: RowAction) =>
  isRowActionDisabled(row, action, buildActionContext(), t)

const onHandle = () => { if (props.detailRow) emit('handle', props.detailRow) }
const onIgnore = () => { if (props.detailRow) emit('ignore', props.detailRow) }
const onEscalate = () => { if (props.detailRow) emit('escalate', props.detailRow) }
</script>

<style scoped>
.detail-content {
  padding: var(--spacing-sm) 0;
}

.detail-actions {
  margin-top: var(--spacing-xl);
  display: flex;
  gap: var(--spacing-md);
}

/* 响应式：移动端适配 */
@media (max-width: 768px) {
  :deep(.el-drawer) {
    width: 90% !important;
  }
}
</style>

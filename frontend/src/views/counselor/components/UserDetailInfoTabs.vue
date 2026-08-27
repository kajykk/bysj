<template>
  <el-tab-pane
    :label="t('counselorUserDetail.tabRiskHistory')"
    name="risk_history"
  >
    <el-timeline
      v-loading="loading"
      class="detail-timeline"
    >
      <el-timeline-item
        v-for="item in riskHistory"
        :key="item.id"
        :type="getRiskTimelineType(item)"
        :timestamp="item.created_at"
        placement="top"
      >
        <div class="timeline-title">
          <el-tag
            size="small"
            :type="getWarningRiskLevelTagType(item.risk_level ?? 0)"
          >
            {{ getWarningRiskLevelLabel(item.risk_level ?? 0) }}
          </el-tag>
        </div>
        <div class="timeline-text">
          {{ t('counselorUserDetail.historyColRiskScore') }}: {{ item.risk_score }}
        </div>
      </el-timeline-item>
    </el-timeline>
    <el-empty
      v-if="!loading && !riskHistory.length"
      :description="t('common.noData')"
    />
  </el-tab-pane>

  <el-tab-pane
    :label="t('counselorUserDetail.tabAssessments')"
    name="assessments"
  >
    <el-table
      :data="assessments"
      border
    >
      <el-table-column
        prop="id"
        :label="t('counselorUserDetail.assessmentColId')"
        width="100"
      />
      <el-table-column
        prop="type"
        :label="t('counselorUserDetail.assessmentColType')"
        min-width="120"
      />
      <el-table-column
        prop="score"
        :label="t('counselorUserDetail.assessmentColScore')"
        min-width="120"
      />
      <el-table-column
        prop="created_at"
        :label="t('counselorUserDetail.assessmentColTime')"
        min-width="180"
      />
    </el-table>
  </el-tab-pane>

  <el-tab-pane
    :label="t('counselorUserDetail.tabInterventions')"
    name="interventions"
  >
    <el-timeline class="detail-timeline">
      <el-timeline-item
        v-for="item in interventions"
        :key="item.id"
        :type="item.status === 'completed' ? 'success' : item.status === 'active' ? 'primary' : 'warning'"
        :timestamp="item.created_at"
        placement="top"
      >
        <div class="timeline-title">
          {{ item.type }}
        </div>
        <div class="timeline-text">
          {{ item.status }}
        </div>
      </el-timeline-item>
    </el-timeline>
    <el-empty
      v-if="!interventions.length"
      :description="t('common.noData')"
    />
  </el-tab-pane>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type {
  UserAssessmentItem,
  UserInterventionItem,
  UserRiskHistoryItem,
} from '@/api/counselorApi'
import {
  getWarningRiskLevelLabel,
  getWarningRiskLevelTagType,
} from '@/utils/warning'

interface Props {
  riskHistory: UserRiskHistoryItem[]
  assessments: UserAssessmentItem[]
  interventions: UserInterventionItem[]
  loading: boolean
}

defineProps<Props>()

const { t } = useI18n()

const getRiskTimelineType = (item: UserRiskHistoryItem) => {
  const tag = getWarningRiskLevelTagType(item.risk_level ?? 0)
  return tag === 'danger' ? 'danger' : tag === 'warning' ? 'warning' : 'primary'
}
</script>

<style scoped>
.detail-timeline {
  padding: var(--spacing-sm) 0 0 6px;
}

.detail-timeline .timeline-title {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}

.detail-timeline .timeline-text {
  color: var(--text-secondary);
  font-size: 13px;
}
</style>

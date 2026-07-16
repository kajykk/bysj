<template>
  <div class="intervention-page">
    <InterventionStatsCard />
    <el-tabs
      v-model="activeTab"
      type="border-card"
      @tab-change="handleTabChange"
    >
      <el-tab-pane
        :label="t('userIntervention.tabActive')"
        name="active"
      >
        <StatefulContainer
          :loading="activeLoading"
          :empty="!activeLoading && !activeData.plan.id"
          :error-message="activeError"
          :empty-text="t('userIntervention.emptyActive')"
          @retry="loadActive"
        >
          <template v-if="activeData.plan.id">
            <ActivePlanCard :plan="activeData.plan" />
            <TodayTasksCard
              :tasks="activeData.tasks"
              :task-pending-ids="taskPendingIds"
              :task-action-type="taskActionType"
              @complete="handleComplete"
              @skip="handleSkip"
              @postpone="openPostpone"
              @feedback="openFeedback"
            />
          </template>
        </StatefulContainer>
      </el-tab-pane>

      <el-tab-pane
        :label="t('userIntervention.tabHistory')"
        name="history"
      >
        <HistoryTab
          :loading="historyLoading"
          :rows="historyRows"
          :total="historyTotal"
          :page="historyPage"
          :page-size="historyPageSize"
          :error-message="historyError"
          @update:page="onPageChange"
          @update:page-size="onPageSizeChange"
          @retry="loadHistory"
        />
      </el-tab-pane>
    </el-tabs>

    <FeedbackDialog
      v-model:visible="feedbackVisible"
      :loading="feedbackSubmitting"
      :initial-score="feedbackInitialScore"
      :initial-note="feedbackInitialNote"
      @submit="submitFeedback"
    />

    <PostponeDialog
      v-model:visible="postponeVisible"
      :loading="postponeSubmitting"
      @submit="submitPostpone"
    />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import ActivePlanCard from './components/user-intervention/ActivePlanCard.vue'
import InterventionStatsCard from './components/user-intervention/InterventionStatsCard.vue'
import TodayTasksCard from './components/user-intervention/TodayTasksCard.vue'
import HistoryTab from './components/user-intervention/HistoryTab.vue'
import FeedbackDialog from './components/user-intervention/FeedbackDialog.vue'
import PostponeDialog from './components/user-intervention/PostponeDialog.vue'
import { useInterventionData } from './components/user-intervention/useInterventionData'

const { t } = useI18n()

const {
  activeTab,
  activeData, activeLoading, activeError,
  taskPendingIds, taskActionType,
  loadActive,
  handleComplete, handleSkip,
  feedbackVisible, feedbackSubmitting,
  feedbackInitialScore, feedbackInitialNote,
  openFeedback, submitFeedback,
  postponeVisible, postponeSubmitting,
  openPostpone, submitPostpone,
  historyRows, historyTotal, historyPage, historyPageSize,
  historyLoading, historyError,
  loadHistory, handleTabChange, onPageChange, onPageSizeChange,
} = useInterventionData()
</script>

<style scoped>
.intervention-page {
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}
</style>

<template>
  <div class="model-training-page">
    <el-row
      :gutter="16"
      class="top-grid"
    >
      <el-col
        :xs="24"
        :sm="24"
        :md="18"
      >
        <el-card class="hero-card console-card">
          <template #header>
            <div class="header-row">
              <div>
                <div class="eyebrow">
                  {{ t('userModelTraining.trainingConsoleEyebrow') }}
                </div>
                <div class="title">
                  {{ t('userModelTraining.title') }}
                </div>
                <div class="subtitle">
                  {{ t('userModelTraining.subtitle') }}
                </div>
              </div>
              <div class="header-status">
                <el-tag
                  type="success"
                  effect="light"
                >
                  {{ t('userModelTraining.statusReady') }}
                </el-tag>
                <el-tag
                  type="info"
                  effect="plain"
                >
                  {{ t('userModelTraining.dualModal') }}
                </el-tag>
              </div>
            </div>
          </template>

          <TrainingStatsRow
            :model-status-summary="modelStatusSummary"
            :can-train="canTrain"
          />

          <el-alert
            type="info"
            show-icon
            :closable="false"
            class="console-alert"
            :title="t('userModelTraining.consoleAlert')"
          />

          <TrainingJobCard
            :active-job="activeJob"
            :active-job-id="activeJobId"
          />

          <el-row
            :gutter="16"
            class="action-grid"
          >
            <el-col :span="12">
              <TrainingActionCard
                :can-train="canTrain"
                :status-loading="statusLoading"
                :training-form="trainingForm"
                @go-to-risk="goToRiskPage"
                @copy-paths="copyModelPaths"
                @open-script="openTrainingScript"
                @refresh="refreshStatus"
                @run-pipeline="runTrainingPipeline"
              />
            </el-col>
            <el-col :span="12">
              <TrainingArtifactsCard
                :can-train="canTrain"
                :model-status-summary="modelStatusSummary"
              />
            </el-col>
          </el-row>

          <TrainingLogCard
            :training-log-rows="trainingLogRows"
            :latest-log="latestLog"
          />
        </el-card>
      </el-col>

      <el-col
        :xs="24"
        :sm="24"
        :md="6"
      >
        <TrainingSidePanel
          :model-status="modelStatus"
          :model-status-loaded-at="modelStatusLoadedAt"
          :can-train="canTrain"
          @go-to-risk="goToRiskPage"
          @scroll-to-artifacts="scrollToArtifacts"
          @show-status-detail="showModelStatusDetail"
        />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import TrainingStatsRow from './components/user-model-training/TrainingStatsRow.vue'
import TrainingJobCard from './components/user-model-training/TrainingJobCard.vue'
import TrainingActionCard from './components/user-model-training/TrainingActionCard.vue'
import TrainingArtifactsCard from './components/user-model-training/TrainingArtifactsCard.vue'
import TrainingLogCard from './components/user-model-training/TrainingLogCard.vue'
import TrainingSidePanel from './components/user-model-training/TrainingSidePanel.vue'
import { useModelTrainingData } from './components/user-model-training/useModelTrainingData'

const { t } = useI18n()

const {
  canTrain,
  statusLoading,
  modelStatusLoadedAt,
  modelStatus,
  modelStatusSummary,
  latestLog,
  trainingLogRows,
  activeJobId,
  activeJob,
  trainingForm,
  refreshStatus,
  runTrainingPipeline,
  goToRiskPage,
  copyModelPaths,
  openTrainingScript,
  scrollToArtifacts,
  showModelStatusDetail,
} = useModelTrainingData()
</script>

<style scoped>
.model-training-page {
  padding: 0;
}

.top-grid {
  align-items: stretch;
}

.console-card,
.hero-card {
  border-radius: 18px;
}

.eyebrow {
  font-size: var(--font-size-extra-small);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.title {
  font-size: var(--font-size-display);
  font-weight: var(--font-weight-bold);
  letter-spacing: var(--letter-spacing-tight);
  line-height: var(--line-height-tight);
  color: var(--text-primary);
}

.subtitle {
  margin-top: 6px;
  color: #6b7280;
  font-size: var(--font-size-small);
}

.header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.header-status {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.console-alert {
  margin-bottom: 16px;
}

.action-grid {
  margin-top: 8px;
}
</style>

<!-- P1-FE-005 修复：全局样式（非 scoped），用于 ElMessageBox 纯文本换行显示 -->
<style>
.model-status-detail-msgbox .el-messagebox__message {
  white-space: pre-line;
  font-family: monospace;
}
</style>

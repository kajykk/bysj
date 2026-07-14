<template>
  <el-card
    shadow="never"
    class="action-card log-card section-card"
  >
    <template #header>
      <div class="header-row">
        <span class="card-title">{{ t('userModelTraining.logPanelTitle') }}</span>
        <div class="header-status">
          <el-tag
            type="info"
            effect="light"
          >
            {{ t('userModelTraining.consoleLog') }}
          </el-tag>
          <el-tag
            v-if="latestLog"
            :type="latestLog.level === 'error' ? 'danger' : latestLog.level === 'warning' ? 'warning' : 'success'"
            effect="dark"
          >
            {{ t('userModelTraining.latestLog', { stage: latestLog.stage }) }}
          </el-tag>
        </div>
      </div>
    </template>
    <el-timeline class="training-timeline">
      <el-timeline-item
        v-for="item in trainingLogRows"
        :key="`${item.time}-${item.stage}-${item.message}`"
        :type="item.level === 'error' ? 'danger' : item.level === 'warning' ? 'warning' : 'primary'"
        :timestamp="item.time"
        placement="top"
      >
        <div class="timeline-title">
          {{ item.stage }}
        </div>
        <div class="timeline-text">
          {{ item.message }}
        </div>
      </el-timeline-item>
    </el-timeline>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { TrainingLogRow } from './sharedModelTrainingUtils'

defineProps<{
  trainingLogRows: TrainingLogRow[]
  latestLog: TrainingLogRow | undefined
}>()

const { t } = useI18n()
</script>

<style scoped>
.action-card {
  min-height: 260px;
  border-radius: 16px;
}

.section-card {
  margin-top: var(--spacing-lg);
}

.log-card {
  border-radius: 16px;
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

.card-title {
  font-weight: var(--font-weight-bold);
}

.training-timeline {
  margin-top: 4px;
}

.timeline-title {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.timeline-text {
  margin-top: 4px;
  color: var(--text-regular);
  line-height: 1.6;
}
</style>

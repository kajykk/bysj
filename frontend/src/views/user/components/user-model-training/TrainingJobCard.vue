<template>
  <el-card
    v-if="activeJob"
    shadow="never"
    class="job-card"
  >
    <template #header>
      <div class="header-row">
        <span class="card-title">{{ t('userModelTraining.activeJobTitle') }}</span>
        <el-tag
          :type="activeJob.status === 'failed' ? 'danger' : activeJob.status === 'completed' ? 'success' : 'warning'"
          effect="light"
        >
          {{ activeJob.status }}
        </el-tag>
      </div>
    </template>
    <el-progress
      :percentage="activeJob.progress || 0"
      :status="activeJob.status === 'failed' ? 'exception' : activeJob.status === 'completed' ? 'success' : undefined"
    />
    <el-descriptions
      :column="3"
      border
      class="job-desc"
    >
      <el-descriptions-item :label="t('userModelTraining.colJobId')">
        {{ activeJob.job_id || activeJobId || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('userModelTraining.colStage')">
        {{ activeJob.stage || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('userModelTraining.colMessage')">
        {{ activeJob.message || '-' }}
      </el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ActiveJob } from './sharedModelTrainingUtils'

defineProps<{
  activeJob: ActiveJob | null
  activeJobId: string
}>()

const { t } = useI18n()
</script>

<style scoped>
.job-card {
  border-radius: 16px;
  margin-bottom: 16px;
}

.header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.card-title {
  font-weight: var(--font-weight-bold);
}

.job-desc :deep(.el-descriptions__label) {
  width: 100px;
}
</style>

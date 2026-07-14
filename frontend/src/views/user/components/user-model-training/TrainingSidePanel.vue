<template>
  <el-card class="side-card console-side-card">
    <template #header>
      <span class="card-title">{{ t('userModelTraining.hintTitle') }}</span>
    </template>
    <ul class="hint-list">
      <li>{{ t('userModelTraining.hint1') }}</li>
      <li>{{ t('userModelTraining.hint2') }}</li>
      <li>{{ t('userModelTraining.hint3') }}</li>
    </ul>
  </el-card>

  <el-card class="side-card console-side-card section-card">
    <template #header>
      <span class="card-title">{{ t('userModelTraining.recentStatusTitle') }}</span>
    </template>
    <div class="status-list">
      <div class="status-item success">
        {{ t('userModelTraining.statusBackend') }}
      </div>
      <div class="status-item success">
        {{ t('userModelTraining.statusFrontend') }}
      </div>
      <div class="status-item info">
        {{ t('userModelTraining.statusEntry') }}
      </div>
      <div class="status-item warning">
        {{ t('userModelTraining.statusAdvice') }}
      </div>
    </div>
    <el-divider />
    <el-descriptions
      :column="1"
      border
      class="compact-desc"
    >
      <el-descriptions-item :label="t('userModelTraining.colModelStatus')">
        {{ modelStatus.ready ? t('userModelTraining.allReady') : t('userModelTraining.partialMissing') }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('userModelTraining.colDetectedAt')">
        {{ modelStatusLoadedAt }}
      </el-descriptions-item>
      <!-- P1-2 角色简化：模型目录路径仅 admin 可见 -->
      <el-descriptions-item
        v-if="canTrain"
        :label="t('userModelTraining.colModelDir')"
      >
        {{ modelStatus.model_dir }}
      </el-descriptions-item>
    </el-descriptions>
  </el-card>

  <el-card class="side-card console-side-card section-card">
    <template #header>
      <span class="card-title">{{ t('userModelTraining.shortcutTitle') }}</span>
    </template>
    <el-space
      direction="vertical"
      fill
      style="width: 100%"
    >
      <el-button @click="emit('goToRisk')">
        {{ t('userModelTraining.riskPanelBtn') }}
      </el-button>
      <el-button @click="emit('scrollToArtifacts')">
        {{ t('userModelTraining.artifactsLocationBtn') }}
      </el-button>
      <el-button @click="emit('showStatusDetail')">
        {{ t('userModelTraining.viewStatusDetailBtn') }}
      </el-button>
    </el-space>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ModelStatusResult } from '@/api/modelApi'

defineProps<{
  modelStatus: ModelStatusResult
  modelStatusLoadedAt: string
  canTrain: boolean
}>()

const emit = defineEmits<{
  goToRisk: []
  scrollToArtifacts: []
  showStatusDetail: []
}>()

const { t } = useI18n()
</script>

<style scoped>
.side-card,
.console-side-card {
  border-radius: 18px;
}

.section-card {
  margin-top: var(--spacing-lg);
}

.card-title {
  font-weight: var(--font-weight-bold);
}

.hint-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
  color: var(--text-primary);
}

.status-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-item {
  border-radius: 12px;
  padding: 10px 12px;
  font-size: var(--font-size-small);
  line-height: 1.5;
  background: #f8fafc;
  color: #334155;
}

.status-item.success {
  background: var(--success-light);
  color: #2f6b1f;
}

.status-item.info {
  background: var(--info-light);
  color: #205a9d;
}

.status-item.warning {
  background: var(--warning-light);
  color: #8a5a12;
}

.compact-desc :deep(.el-descriptions__label) {
  width: 120px;
}
</style>

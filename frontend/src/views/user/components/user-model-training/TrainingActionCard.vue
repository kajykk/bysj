<template>
  <el-card
    shadow="never"
    class="action-card"
  >
    <template #header>
      <span class="card-title">{{ t('userModelTraining.actionTitle') }}</span>
    </template>
    <div class="action-list">
      <el-button
        type="primary"
        @click="emit('goToRisk')"
      >
        {{ t('userModelTraining.goToRiskBtn') }}
      </el-button>
      <!-- P1-2 角色简化：复制路径/查看脚本仅 admin 可见 -->
      <el-button
        v-if="canTrain"
        @click="emit('copyPaths')"
      >
        {{ t('userModelTraining.copyPathsBtn') }}
      </el-button>
      <el-button
        v-if="canTrain"
        type="success"
        plain
        @click="emit('openScript')"
      >
        {{ t('userModelTraining.viewScriptBtn') }}
      </el-button>
      <el-button
        :loading="statusLoading"
        @click="emit('refresh')"
      >
        {{ t('userModelTraining.refreshBtn') }}
      </el-button>
      <el-button
        v-if="canTrain"
        type="danger"
        plain
        :loading="statusLoading"
        @click="emit('runPipeline')"
      >
        {{ t('userModelTraining.runPipelineBtn') }}
      </el-button>
    </div>
    <!-- ISS-001 修复：训练参数可配置表单（仅 admin 可见） -->
    <el-form
      v-if="canTrain"
      :model="trainingForm"
      label-width="120px"
      class="training-form"
      size="small"
    >
      <el-form-item :label="t('userModelTraining.formLabelDataset')">
        <el-input
          v-model="trainingForm.dataset_name"
          placeholder="depression_multimodal_v1"
        />
      </el-form-item>
      <el-form-item :label="t('userModelTraining.formLabelModel')">
        <el-input
          v-model="trainingForm.model_name"
          placeholder="text_bert_classifier"
        />
      </el-form-item>
      <el-form-item :label="t('userModelTraining.formLabelEpochs')">
        <el-input-number
          v-model="trainingForm.epochs"
          :min="1"
          :max="100"
          :step="1"
        />
      </el-form-item>
      <el-form-item :label="t('userModelTraining.formLabelBatchSize')">
        <el-input-number
          v-model="trainingForm.batch_size"
          :min="1"
          :max="256"
          :step="1"
        />
      </el-form-item>
      <el-form-item :label="t('userModelTraining.formLabelLearningRate')">
        <el-input-number
          v-model="trainingForm.learning_rate"
          :min="0"
          :max="1"
          :step="0.00001"
          :precision="6"
        />
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { TrainingForm } from './sharedModelTrainingUtils'

defineProps<{
  canTrain: boolean
  statusLoading: boolean
  trainingForm: TrainingForm
}>()

const emit = defineEmits<{
  goToRisk: []
  copyPaths: []
  openScript: []
  refresh: []
  runPipeline: []
}>()

const { t } = useI18n()
</script>

<style scoped>
.action-card {
  min-height: 260px;
  border-radius: 16px;
}

.card-title {
  font-weight: var(--font-weight-bold);
}

.action-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>

<template>
  <el-card
    shadow="never"
    class="action-card"
  >
    <template #header>
      <span class="card-title">{{ t('userModelTraining.artifactsTitle') }}</span>
    </template>
    <!-- P1-2 角色简化：Artifacts 文件路径仅 admin 可见，学生看到状态摘要 -->
    <el-descriptions
      v-if="canTrain"
      :column="1"
      border
      class="compact-desc"
    >
      <el-descriptions-item :label="t('userModelTraining.artifactStructured')">
        models/artifacts/depression_tabular/best_model.pkl
      </el-descriptions-item>
      <el-descriptions-item :label="t('userModelTraining.artifactText')">
        models/artifacts/text_depression_classifier/text_model.pkl
      </el-descriptions-item>
      <el-descriptions-item :label="t('userModelTraining.artifactVectorizer')">
        models/artifacts/text_depression_classifier/text_tfidf.pkl
      </el-descriptions-item>
      <el-descriptions-item :label="t('userModelTraining.artifactEntry')">
        train_ml_oneclick.ps1
      </el-descriptions-item>
    </el-descriptions>
    <el-descriptions
      v-else
      :column="1"
      border
      class="compact-desc"
    >
      <el-descriptions-item :label="t('userModelTraining.artifactStructured')">
        {{ modelStatusSummary.structured }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('userModelTraining.artifactText')">
        {{ modelStatusSummary.text }}
      </el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  canTrain: boolean
  modelStatusSummary: { structured: string; text: string }
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

.compact-desc :deep(.el-descriptions__label) {
  width: 120px;
}
</style>

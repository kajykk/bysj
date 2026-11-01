<template>
  <el-row
    :gutter="12"
    class="stats-row"
  >
    <el-col :span="8">
      <div class="stat-card accent-blue">
        <div class="stat-label">
          {{ t('userModelTraining.statStructured') }}
        </div>
        <div class="stat-value">
          {{ modelStatusSummary.structured }}
        </div>
        <!-- P1-2 角色简化：文件名仅 admin 可见，学生看到通用描述 -->
        <div class="stat-desc">
          {{ canTrain ? 'best_model.pkl' : t('userModelTraining.statStructuredDesc') }}
        </div>
      </div>
    </el-col>
    <el-col :span="8">
      <div class="stat-card accent-green">
        <div class="stat-label">
          {{ t('userModelTraining.statText') }}
        </div>
        <div class="stat-value">
          {{ modelStatusSummary.text }}
        </div>
        <div class="stat-desc">
          {{ canTrain ? 'text_model.pkl + tfidf.pkl' : t('userModelTraining.statTextDesc') }}
        </div>
      </div>
    </el-col>
    <el-col :span="8">
      <div class="stat-card accent-gold">
        <div class="stat-label">
          {{ t('userModelTraining.statScript') }}
        </div>
        <div class="stat-value">
          {{ t('userModelTraining.statScriptValue') }}
        </div>
        <div class="stat-desc">
          {{ canTrain ? 'train_ml_oneclick.ps1' : t('userModelTraining.statScriptDesc') }}
        </div>
      </div>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  modelStatusSummary: { structured: string; text: string }
  canTrain: boolean
}>()

const { t } = useI18n()
</script>

<style scoped>
.stats-row {
  margin-bottom: 16px;
}

.stat-card {
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  min-height: 106px;
  box-shadow: var(--shadow-card);
}

/* 蓝底在浅色主题是深蓝（白字 5.3:1），暗色主题被提亮成浅蓝（白字仅 3.0:1），
   所以用跟随主题的 --text-on-accent；绿/金底两套主题都偏亮，固定深墨色。 */
.accent-blue {
  background: var(--gradient-blue);
  color: var(--text-on-accent);
}

.accent-green {
  background: var(--gradient-green);
  color: var(--text-on-light-accent);
}

.accent-gold {
  background: var(--gradient-gold);
  color: var(--text-on-light-accent);
}

.stat-label {
  font-size: var(--font-size-extra-small);
}

.stat-value {
  margin-top: 8px;
  font-size: var(--font-size-heading);
  font-weight: 800;
}

.stat-desc {
  margin-top: 4px;
  font-size: var(--font-size-extra-small);
}
</style>

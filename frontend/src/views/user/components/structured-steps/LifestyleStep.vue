<template>
  <div>
    <el-form-item
      :label="t('structuredAssess.fieldSleepDuration')"
      prop="sleep_duration"
    >
      <div class="slider-with-value">
        <el-slider
          v-model="form.sleep_duration"
          :min="0"
          :max="12"
          :step="0.5"
          show-input
        />
        <span class="slider-value-label">{{ t('structuredAssess.sliderValueSleep', { value: form.sleep_duration }) }}</span>
      </div>
    </el-form-item>
    <el-form-item
      :label="t('structuredAssess.fieldExerciseFrequency')"
      prop="exercise_frequency"
    >
      <div class="slider-with-value">
        <el-slider
          v-model="form.exercise_frequency"
          :min="0"
          :max="7"
          :step="1"
          show-input
        />
        <span class="slider-value-label">{{ t('structuredAssess.sliderValueExercise', { value: form.exercise_frequency }) }}</span>
      </div>
    </el-form-item>
    <el-form-item
      :label="t('structuredAssess.fieldSocialSupport')"
      prop="social_support"
    >
      <div class="slider-with-value">
        <el-slider
          v-model="form.social_support"
          :min="0"
          :max="5"
          :step="1"
          show-input
        />
        <span class="slider-value-label">{{ t('structuredAssess.sliderValueSupport', { value: form.social_support }) }}</span>
      </div>
    </el-form-item>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { StructuredForm } from './sharedStepUtils'

const form = defineModel<StructuredForm>('form', { required: true })

const { t } = useI18n()
</script>

<style scoped>
.slider-with-value {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.slider-with-value .el-slider {
  flex: 1;
}

.slider-value-label {
  font-size: 13px;
  color: #5a6470;
  font-weight: 500;
  min-width: 60px;
  text-align: right;
}
</style>

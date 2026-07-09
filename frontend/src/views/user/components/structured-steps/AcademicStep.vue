<template>
  <div>
    <el-form-item
      :label="t('structuredAssess.fieldCgpa')"
      prop="cgpa"
    >
      <div class="slider-with-value">
        <el-slider
          v-model="form.cgpa"
          :min="0"
          :max="10"
          :step="0.1"
          show-input
        />
        <span class="slider-value-label">{{ t('structuredAssess.sliderValueCgpa', { value: form.cgpa.toFixed(1) }) }}</span>
      </div>
    </el-form-item>
    <el-form-item
      :label="t('structuredAssess.fieldAcademicPressure')"
      prop="academic_pressure"
    >
      <div class="slider-with-value">
        <el-slider
          v-model="form.academic_pressure"
          :min="0"
          :max="5"
          :step="1"
          show-input
        />
        <span class="slider-value-label">{{ t('structuredAssess.sliderValuePressure', { value: form.academic_pressure }) }}</span>
      </div>
    </el-form-item>
    <el-form-item
      :label="t('structuredAssess.fieldFinancialPressure')"
      prop="financial_pressure"
    >
      <div class="slider-with-value">
        <el-slider
          v-model="form.financial_pressure"
          :min="0"
          :max="5"
          :step="1"
          show-input
        />
        <span class="slider-value-label">{{ t('structuredAssess.sliderValuePressure', { value: form.financial_pressure }) }}</span>
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
  font-size: var(--font-size-small);
  color: #5a6470;
  font-weight: 500;
  min-width: 60px;
  text-align: right;
}
</style>

<template>
  <div>
    <el-form-item
      :label="t('structuredAssess.fieldStressLevel')"
      prop="stress_level"
    >
      <div class="slider-with-value">
        <el-slider
          v-model="form.stress_level"
          :min="0"
          :max="5"
          :step="1"
          show-input
        />
        <span class="slider-value-label">{{ t('structuredAssess.sliderValuePressure', { value: form.stress_level }) }}</span>
      </div>
    </el-form-item>
    <el-form-item
      :label="t('structuredAssess.fieldAnxiety')"
      prop="anxiety"
    >
      <div class="slider-with-value">
        <el-slider
          v-model="form.anxiety"
          :min="0"
          :max="5"
          :step="1"
          show-input
        />
        <span class="slider-value-label">{{ t('structuredAssess.sliderValuePressure', { value: form.anxiety }) }}</span>
      </div>
    </el-form-item>
    <el-form-item
      :label="t('structuredAssess.fieldFamilyHistory')"
      prop="family_history"
    >
      <el-select
        v-model="form.family_history"
        style="width: 100%"
      >
        <el-option
          :label="t('structuredAssess.optionNone')"
          :value="0"
        />
        <el-option
          :label="t('structuredAssess.optionHave')"
          :value="1"
        />
      </el-select>
    </el-form-item>
    <el-form-item
      :label="t('structuredAssess.fieldPanicAttack')"
      prop="panic_attack"
    >
      <el-select
        v-model="form.panic_attack"
        style="width: 100%"
      >
        <el-option
          :label="t('structuredAssess.optionNone')"
          :value="0"
        />
        <el-option
          :label="t('structuredAssess.optionHave')"
          :value="1"
        />
      </el-select>
    </el-form-item>
    <el-form-item
      :label="t('structuredAssess.fieldTreatmentSeeking')"
      prop="treatment_seeking"
    >
      <el-select
        v-model="form.treatment_seeking"
        style="width: 100%"
      >
        <el-option
          :label="t('structuredAssess.noOption')"
          :value="0"
        />
        <el-option
          :label="t('structuredAssess.yesOption')"
          :value="1"
        />
      </el-select>
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

<template>
  <div>
    <el-form-item
      :label="t('structuredAssess.fieldIdentityType')"
      prop="identity_type"
    >
      <el-radio-group v-model="form.identity_type">
        <el-radio value="student">
          {{ t('structuredAssess.optionStudent') }}
        </el-radio>
        <el-radio value="worker">
          {{ t('structuredAssess.optionWorker') }}
        </el-radio>
      </el-radio-group>
    </el-form-item>
    <el-form-item
      :label="t('structuredAssess.fieldAge')"
      prop="age"
    >
      <el-input-number
        v-model="form.age"
        :min="15"
        :max="60"
      />
    </el-form-item>
    <el-form-item
      :label="t('structuredAssess.fieldGender')"
      prop="gender"
    >
      <el-select
        v-model="form.gender"
        style="width: 100%"
      >
        <el-option
          :label="t('structuredAssess.optionMale')"
          :value="1"
        />
        <el-option
          :label="t('structuredAssess.optionFemale')"
          :value="0"
        />
      </el-select>
    </el-form-item>
    <el-form-item
      v-if="form.identity_type === 'student'"
      :label="t('structuredAssess.fieldStudyYear')"
      prop="study_year"
    >
      <el-input-number
        v-model="form.study_year"
        :min="1"
        :max="6"
      />
    </el-form-item>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { StructuredForm } from './sharedStepUtils'

const form = defineModel<StructuredForm>('form', { required: true })

const { t } = useI18n()
</script>

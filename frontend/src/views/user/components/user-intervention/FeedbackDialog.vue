<template>
  <el-dialog
    :model-value="visible"
    :title="t('userIntervention.feedbackDialogTitle')"
    width="420px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form label-width="80px">
      <el-form-item :label="t('userIntervention.feedbackScoreLabel')">
        <el-rate
          v-model="form.score"
          :max="5"
          show-score
        />
      </el-form-item>
      <el-form-item :label="t('userIntervention.feedbackNoteLabel')">
        <el-input
          v-model="form.note"
          type="textarea"
          :rows="3"
          :placeholder="t('userIntervention.feedbackNotePlaceholder')"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:visible', false)">
        {{ t('common.cancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="loading"
        @click="emit('submit', { score: form.score, note: form.note })"
      >
        {{ t('userIntervention.btnSubmit') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FeedbackSubmitPayload } from './useInterventionData'

const props = defineProps<{
  visible: boolean
  loading: boolean
  initialScore: number
  initialNote: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'submit', payload: FeedbackSubmitPayload): void
}>()

const { t } = useI18n()

// 表单状态随对话框打开重置（匹配原 openFeedback 行为：score 回填已有评分，note 回填已有备注）
const form = reactive<{ score: number; note: string }>({
  score: 3,
  note: ''
})

watch(
  () => props.visible,
  (val) => {
    if (val) {
      form.score = props.initialScore
      form.note = props.initialNote
    }
  }
)
</script>

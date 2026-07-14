<template>
  <el-dialog
    :model-value="visible"
    :title="t('userIntervention.postponeDialogTitle')"
    width="420px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form label-width="80px">
      <el-form-item :label="t('userIntervention.postponeDateLabel')">
        <el-date-picker
          v-model="form.date"
          type="date"
          value-format="YYYY-MM-DD"
          :placeholder="t('userIntervention.postponeDatePlaceholder')"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('userIntervention.feedbackNoteLabel')">
        <el-input
          v-model="form.note"
          type="textarea"
          :rows="2"
          :placeholder="t('userIntervention.postponeNotePlaceholder')"
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
        :disabled="!form.date"
        @click="emit('submit', { date: form.date, note: form.note })"
      >
        {{ t('userIntervention.btnConfirmPostpone') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PostponeSubmitPayload } from './useInterventionData'

const props = defineProps<{
  visible: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'submit', payload: PostponeSubmitPayload): void
}>()

const { t } = useI18n()

// 表单状态随对话框打开重置（匹配原 openPostpone 行为：date/note 清空）
const form = reactive<{ date: string; note: string }>({
  date: '',
  note: ''
})

watch(
  () => props.visible,
  (val) => {
    if (val) {
      form.date = ''
      form.note = ''
    }
  }
)
</script>

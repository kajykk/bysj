<template>
  <!-- ISS-072 修复：升级对话框 -->
  <el-dialog
    :model-value="visible"
    :title="t('adminCrisisEvents.escalateDialogTitle')"
    width="500px"
    destroy-on-close
    :focus-on-close="true"
    @update:model-value="emit('update:visible', $event)"
  >
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="dialog-alert"
    >
      {{ t('adminCrisisEvents.escalateAlert') }}
    </el-alert>
    <el-form label-width="100px">
      <el-form-item :label="t('adminCrisisEvents.handleEventId')">
        <span>{{ event?.id }}</span>
      </el-form-item>
      <el-form-item :label="t('adminCrisisEvents.escalateReason')">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="3"
          :placeholder="t('adminCrisisEvents.escalateReasonPlaceholder')"
          maxlength="2000"
          show-word-limit
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:visible', false)">
        {{ t('common.cancel') }}
      </el-button>
      <el-button
        type="warning"
        :loading="loading"
        :disabled="!form.reason.trim()"
        @click="emit('submit', { reason: form.reason })"
      >
        {{ t('adminCrisisEvents.escalateConfirmBtn') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { CrisisEventItem } from '@/api/adminApi'

const props = defineProps<{
  visible: boolean
  event: CrisisEventItem | null
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'submit', payload: { reason: string }): void
}>()

const { t } = useI18n()

// 表单状态随对话框打开重置（匹配原 openEscalateDialog 行为）
const form = reactive<{ reason: string }>({ reason: '' })

watch(
  () => props.visible,
  (val) => {
    if (val) {
      form.reason = ''
    }
  }
)
</script>

<style scoped>
.dialog-alert {
  margin-bottom: var(--spacing-md);
}
</style>

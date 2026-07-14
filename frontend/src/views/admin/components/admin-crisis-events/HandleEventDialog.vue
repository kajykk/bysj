<template>
  <!-- ISS-072 修复：处理对话框 -->
  <el-dialog
    :model-value="visible"
    :title="t('adminCrisisEvents.handleDialogTitle')"
    width="500px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form label-width="100px">
      <el-form-item :label="t('adminCrisisEvents.handleEventId')">
        <span>{{ event?.id }}</span>
      </el-form-item>
      <el-form-item :label="t('adminCrisisEvents.handleAction')">
        <el-select
          v-model="form.action"
          :placeholder="t('adminCrisisEvents.handleActionPlaceholder')"
          style="width: 100%"
        >
          <el-option
            :label="t('adminCrisisEvents.handleActionOptions.notifyCounselor')"
            value="notify_counselor"
          />
          <el-option
            :label="t('adminCrisisEvents.handleActionOptions.emergencyContact')"
            value="emergency_contact"
          />
          <el-option
            :label="t('adminCrisisEvents.handleActionOptions.resolved')"
            value="resolved"
          />
          <el-option
            :label="t('adminCrisisEvents.handleActionOptions.escalate')"
            value="escalate"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('adminCrisisEvents.handleNote')">
        <el-input
          v-model="form.note"
          type="textarea"
          :rows="3"
          :placeholder="t('adminCrisisEvents.handleNotePlaceholder')"
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
        type="primary"
        :loading="loading"
        @click="emit('submit', { action: form.action, note: form.note })"
      >
        {{ t('adminCrisisEvents.handleConfirmBtn') }}
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
  (e: 'submit', payload: { action: string; note: string }): void
}>()

const { t } = useI18n()

// 表单状态随对话框打开重置（匹配原 openHandleDialog 行为）
const form = reactive<{ action: string; note: string }>({
  action: 'notify_counselor',
  note: ''
})

watch(
  () => props.visible,
  (val) => {
    if (val) {
      form.action = 'notify_counselor'
      form.note = ''
    }
  }
)
</script>

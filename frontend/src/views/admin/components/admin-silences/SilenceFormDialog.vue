<template>
  <el-dialog
    :model-value="visible"
    :title="isEditMode ? t('adminSilences.editDialogTitle') : t('adminSilences.createDialogTitle')"
    width="600px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="formRules"
      label-width="100px"
    >
      <el-form-item
        :label="t('adminSilences.formName')"
        prop="name"
      >
        <el-input
          v-model="form.name"
          :placeholder="t('adminSilences.formNamePlaceholder')"
          maxlength="200"
          show-word-limit
        />
      </el-form-item>
      <el-form-item
        :label="t('adminSilences.formMatcher')"
        prop="matcherJson"
      >
        <el-input
          v-model="form.matcherJson"
          type="textarea"
          :rows="5"
          :placeholder="t('adminSilences.formMatcherPlaceholder')"
        />
        <div class="hint">
          {{ t('adminSilences.formMatcherHint') }}
        </div>
      </el-form-item>
      <el-form-item
        :label="t('adminSilences.formRange')"
        prop="range"
      >
        <el-date-picker
          v-model="form.range"
          type="datetimerange"
          value-format="YYYY-MM-DDTHH:mm:ss"
          :range-separator="t('adminSilences.rangeSeparator')"
          :start-placeholder="t('adminSilences.rangeStart')"
          :end-placeholder="t('adminSilences.rangeEnd')"
          style="width: 100%"
        />
        <div class="hint">
          {{ t('adminSilences.formRangeHint') }}
        </div>
      </el-form-item>
      <el-form-item
        :label="t('adminSilences.formComment')"
        prop="comment"
      >
        <el-input
          v-model="form.comment"
          type="textarea"
          :rows="2"
          :placeholder="t('adminSilences.formCommentPlaceholder')"
          maxlength="1000"
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
        @click="handleSubmit"
      >
        {{ isEditMode ? t('common.save') : t('common.create') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import type { SilenceCreatePayload, SilenceItem } from '@/api/alertsApi'
import { DEFAULT_MATCHER_JSON } from './sharedSilencesUtils'

const props = defineProps<{
  visible: boolean
  isEditMode: boolean
  loading: boolean
  editingRow: SilenceItem | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'submit', payload: SilenceCreatePayload): void
}>()

const { t } = useI18n()

interface SilenceForm {
  name: string
  matcherJson: string
  range: string[]
  comment: string
}

const form = reactive<SilenceForm>({
  name: '',
  matcherJson: DEFAULT_MATCHER_JSON,
  range: [],
  comment: ''
})

const formRef = ref<FormInstance>()

const formRules: FormRules = {
  name: [
    { required: true, message: t('adminSilences.formNameRequired'), trigger: 'blur' },
    { max: 200, message: t('adminSilences.formNameMaxLength'), trigger: 'blur' }
  ],
  matcherJson: [
    { required: true, message: t('adminSilences.formMatcherRequired'), trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (!value) return callback(new Error(t('adminSilences.formMatcherRequired')))
        try {
          const parsed = JSON.parse(value)
          if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
            return callback(new Error(t('adminSilences.formMatcherNotObject')))
          }
          if (Object.keys(parsed).length === 0) {
            return callback(new Error(t('adminSilences.formMatcherEmpty')))
          }
          callback()
        } catch {
          callback(new Error(t('adminSilences.formMatcherJsonInvalid')))
        }
      },
      trigger: 'blur'
    }
  ],
  range: [
    {
      validator: (_rule, value: string[], callback) => {
        if (!value || value.length !== 2 || !value[0] || !value[1]) {
          return callback(new Error(t('adminSilences.formRangeRequired')))
        }
        callback()
      },
      trigger: 'change'
    }
  ]
}

// 对话框打开时根据模式初始化表单（匹配原 openCreate/openEdit 行为）
watch(
  () => props.visible,
  (val) => {
    if (!val) return
    if (props.isEditMode && props.editingRow) {
      const row = props.editingRow
      form.name = row.name
      try {
        form.matcherJson = JSON.stringify(row.matcher || {}, null, 2)
      } catch {
        form.matcherJson = DEFAULT_MATCHER_JSON
      }
      const startsAt = row.starts_at ? row.starts_at.slice(0, 19) : ''
      const endsAt = row.ends_at ? row.ends_at.slice(0, 19) : ''
      form.range = startsAt && endsAt ? [startsAt, endsAt] : []
      form.comment = row.comment || ''
    } else {
      form.name = ''
      form.matcherJson = DEFAULT_MATCHER_JSON
      form.range = []
      form.comment = ''
    }
  }
)

const handleSubmit = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  let matcher: Record<string, string>
  try {
    matcher = JSON.parse(form.matcherJson)
  } catch {
    ElMessage.error(t('adminSilences.formMatcherJsonInvalid'))
    return
  }

  const payload: SilenceCreatePayload = {
    name: form.name,
    matcher,
    starts_at: form.range[0],
    ends_at: form.range[1],
    comment: form.comment || null
  }

  emit('submit', payload)
}
</script>

<style scoped>
.hint {
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
  line-height: 1.4;
  margin-top: 4px;
}
</style>

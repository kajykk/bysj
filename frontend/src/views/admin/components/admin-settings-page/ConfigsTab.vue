<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span class="card-title">{{ t('adminSettings.configs.cardTitle') }}</span>
        <el-button
          type="primary"
          size="small"
          @click="openConfigCreate"
        >
          {{ t('adminSettings.configs.createBtn') }}
        </el-button>
      </div>
    </template>

    <StatefulContainer
      :loading="loading"
      :empty="!loading && configs.length === 0"
      :error-message="error"
      :empty-text="t('adminSettings.configs.empty')"
      @retry="emit('reload')"
    >
      <el-table
        :data="configs"
        border
        stripe
      >
        <el-table-column
          prop="config_key"
          :label="t('adminSettings.configs.colKey')"
          min-width="180"
        />
        <el-table-column
          prop="config_value"
          :label="t('adminSettings.configs.colValue')"
          min-width="240"
        >
          <template #default="{ row }">
            <span class="config-value">{{ JSON.stringify(row.config_value) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="description"
          :label="t('adminSettings.configs.colDescription')"
          min-width="180"
        >
          <template #default="{ row }">
            {{ row.description || '-' }}
          </template>
        </el-table-column>
        <el-table-column
          :label="t('adminSettings.configs.colOperation')"
          width="100"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              size="small"
              @click="openConfigEdit(row)"
            >
              {{ t('adminSettings.common.edit') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </StatefulContainer>
  </el-card>

  <el-dialog
    v-model="configFormVisible"
    :title="configEditing ? t('adminSettings.configs.editDialogTitle') : t('adminSettings.configs.createDialogTitle')"
    width="480px"
    destroy-on-close
  >
    <el-form
      :model="configForm"
      label-width="100px"
    >
      <el-form-item
        :label="t('adminSettings.configs.formKey')"
        required
      >
        <el-input
          v-model="configForm.config_key"
          :disabled="!!configEditing"
        />
      </el-form-item>
      <el-form-item
        :label="t('adminSettings.configs.formValue')"
        required
      >
        <el-input
          v-model="configValueJson"
          type="textarea"
          :rows="4"
          placeholder="{&quot;value&quot;: &quot;example&quot;}"
        />
      </el-form-item>
      <el-form-item :label="t('adminSettings.configs.formDescription')">
        <el-input v-model="configForm.description" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="configFormVisible = false">
        {{ t('common.cancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="configSaving"
        @click="submitConfig"
      >
        {{ t('common.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
defineOptions({ name: 'ConfigsTab' })
import { reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import { adminApi, type ConfigItem } from '@/api/adminApi'
import { normalizeHttpError } from '@/utils/errorPolicy'

const props = defineProps<{
  configs: ConfigItem[]
  loading: boolean
  error: string
}>()

const emit = defineEmits<{ reload: [] }>()

const { t } = useI18n()

const configFormVisible = ref(false)
const configSaving = ref(false)
const configEditing = ref(false)
const configForm = reactive({ config_key: '', description: '' })
const configValueJson = ref('{}')

const openConfigCreate = () => {
  configEditing.value = false
  configForm.config_key = ''
  configForm.description = ''
  configValueJson.value = '{}'
  configFormVisible.value = true
}

const openConfigEdit = (row: ConfigItem) => {
  configEditing.value = true
  configForm.config_key = row.config_key
  configForm.description = row.description || ''
  configValueJson.value = JSON.stringify(row.config_value, null, 2)
  configFormVisible.value = true
}

const submitConfig = async () => {
  if (!configForm.config_key.trim()) { ElMessage.warning(t('adminSettings.configs.errorKeyRequired')); return }
  let configValue: Record<string, unknown>
  try { configValue = JSON.parse(configValueJson.value) } catch { ElMessage.warning(t('adminSettings.configs.errorJsonInvalid')); return }
  configSaving.value = true
  try {
    await adminApi.upsertAdminConfig({ config_key: configForm.config_key, config_value: configValue, description: configForm.description || undefined })
    ElMessage.success(t('adminSettings.configs.saved'))
    configFormVisible.value = false
    emit('reload')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('adminSettings.configs.saveFailed')).detail)
  } finally {
    configSaving.value = false
  }
}
</script>

<style scoped>
.card-title {
  font-weight: var(--font-weight-semibold);
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.config-value {
  font-family: monospace;
  font-size: var(--font-size-extra-small);
  color: var(--text-regular);
  word-break: break-all;
}
</style>

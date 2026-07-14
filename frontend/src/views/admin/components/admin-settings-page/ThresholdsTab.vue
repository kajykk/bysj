<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span class="card-title">{{ t('adminSettings.thresholds.cardTitle') }}</span>
        <el-button
          type="primary"
          size="small"
          @click="openThresholdCreate"
        >
          {{ t('adminSettings.thresholds.createBtn') }}
        </el-button>
      </div>
    </template>

    <StatefulContainer
      :loading="thresholdLoading"
      :empty="!thresholdLoading && thresholds.length === 0"
      :error-message="thresholdError"
      :empty-text="t('adminSettings.thresholds.empty')"
      @retry="loadThresholds"
    >
      <el-table
        :data="thresholds"
        border
        stripe
      >
        <el-table-column
          prop="level"
          :label="t('adminSettings.thresholds.colLevel')"
          width="80"
        />
        <el-table-column
          prop="level_name"
          :label="t('adminSettings.thresholds.colLevelName')"
          width="120"
        />
        <el-table-column
          prop="min_score"
          :label="t('adminSettings.thresholds.colMinScore')"
          width="100"
        />
        <el-table-column
          prop="max_score"
          :label="t('adminSettings.thresholds.colMaxScore')"
          width="100"
        />
        <el-table-column
          prop="color"
          :label="t('adminSettings.thresholds.colColor')"
          width="100"
        >
          <template #default="{ row }">
            <span :style="{ color: row.color, fontWeight: 'bold' }">{{ row.color }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="action_required"
          :label="t('adminSettings.thresholds.colActionRequired')"
          min-width="200"
        />
        <el-table-column
          :label="t('adminSettings.thresholds.colOperation')"
          width="100"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              size="small"
              @click="openThresholdEdit(row)"
            >
              {{ t('adminSettings.common.edit') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </StatefulContainer>
  </el-card>

  <el-dialog
    v-model="thresholdFormVisible"
    :title="thresholdEditing ? t('adminSettings.thresholds.editDialogTitle') : t('adminSettings.thresholds.createDialogTitle')"
    width="480px"
    destroy-on-close
  >
    <el-form
      :model="thresholdForm"
      label-width="100px"
    >
      <el-form-item
        :label="t('adminSettings.thresholds.formLevel')"
        required
      >
        <el-input-number
          v-model="thresholdForm.level"
          :min="0"
          :max="10"
          :disabled="!!thresholdEditing"
        />
      </el-form-item>
      <el-form-item
        :label="t('adminSettings.thresholds.formLevelName')"
        required
      >
        <el-input v-model="thresholdForm.level_name" />
      </el-form-item>
      <el-form-item
        :label="t('adminSettings.thresholds.formMinScore')"
        required
      >
        <el-input-number
          v-model="thresholdForm.min_score"
          :min="0"
          :max="100"
          :precision="1"
        />
      </el-form-item>
      <el-form-item
        :label="t('adminSettings.thresholds.formMaxScore')"
        required
      >
        <el-input-number
          v-model="thresholdForm.max_score"
          :min="0"
          :max="100"
          :precision="1"
        />
      </el-form-item>
      <el-form-item
        :label="t('adminSettings.thresholds.formColor')"
        required
      >
        <el-input
          v-model="thresholdForm.color"
          placeholder="#d4923a"
        />
      </el-form-item>
      <el-form-item
        :label="t('adminSettings.thresholds.formActionRequired')"
        required
      >
        <el-input
          v-model="thresholdForm.action_required"
          type="textarea"
          :rows="2"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="thresholdFormVisible = false">
        {{ t('common.cancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="thresholdSaving"
        @click="submitThreshold"
      >
        {{ t('common.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
defineOptions({ name: 'ThresholdsTab' })
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import { adminApi, type ThresholdItem } from '@/api/adminApi'
import { normalizeHttpError } from '@/utils/errorPolicy'

const { t } = useI18n()

const thresholds = ref<ThresholdItem[]>([])
const thresholdLoading = ref(false)
const thresholdError = ref('')

const loadThresholds = async () => {
  thresholdLoading.value = true
  thresholdError.value = ''
  try {
    const data = await adminApi.listAdminThresholds()
    thresholds.value = data.items
  } catch (error) {
    thresholdError.value = normalizeHttpError(error, t('adminSettings.thresholds.loadFailed')).detail
  } finally {
    thresholdLoading.value = false
  }
}

const thresholdFormVisible = ref(false)
const thresholdSaving = ref(false)
const thresholdEditing = ref(false)
const thresholdForm = reactive({ level: 0, level_name: '', min_score: 0, max_score: 100, color: '#d4923a', action_required: '' })

const openThresholdCreate = () => {
  thresholdEditing.value = false
  thresholdForm.level = 0
  thresholdForm.level_name = ''
  thresholdForm.min_score = 0
  thresholdForm.max_score = 100
  thresholdForm.color = '#d4923a'
  thresholdForm.action_required = ''
  thresholdFormVisible.value = true
}

const openThresholdEdit = (row: ThresholdItem) => {
  thresholdEditing.value = true
  thresholdForm.level = row.level
  thresholdForm.level_name = row.level_name
  thresholdForm.min_score = row.min_score
  thresholdForm.max_score = row.max_score
  thresholdForm.color = row.color
  thresholdForm.action_required = row.action_required
  thresholdFormVisible.value = true
}

const submitThreshold = async () => {
  if (!thresholdForm.level_name.trim()) { ElMessage.warning(t('adminSettings.thresholds.errorLevelNameRequired')); return }
  if (thresholdForm.min_score > thresholdForm.max_score) { ElMessage.warning(t('adminSettings.thresholds.errorScoreRange')); return }
  thresholdSaving.value = true
  try {
    await adminApi.upsertAdminThreshold({ ...thresholdForm })
    ElMessage.success(t('adminSettings.thresholds.saved'))
    thresholdFormVisible.value = false
    loadThresholds()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, t('adminSettings.thresholds.saveFailed')).detail)
  } finally {
    thresholdSaving.value = false
  }
}

onMounted(() => {
  loadThresholds()
})
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
</style>

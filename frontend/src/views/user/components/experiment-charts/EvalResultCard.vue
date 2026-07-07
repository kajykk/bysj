<template>
  <el-card style="margin-top: 16px">
    <template #header>
      <div class="header-row">
        <span class="card-title">{{ t('experimentAssess.evalResultTitle') }}</span>
        <el-button
          size="small"
          @click="copyJson({ summary, confusionMatrix, evalLogRows, trainLogRows })"
        >
          {{ t('experimentAssess.copyResult') }}
        </el-button>
      </div>
    </template>
    <el-descriptions
      v-if="summary"
      :column="2"
      border
    >
      <el-descriptions-item :label="t('experimentAssess.labelTrainLoss')">
        {{ summary.train_loss }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('experimentAssess.labelValLoss')">
        {{ summary.val_loss }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('experimentAssess.labelValAccuracy')">
        {{ summary.val_accuracy }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('experimentAssess.labelModelStatus')">
        {{ summary.status || 'completed' }}
      </el-descriptions-item>
    </el-descriptions>
    <div
      v-if="trainLogRows.length || evalLogRows.length"
      class="log-viewer-grid"
    >
      <el-card
        v-if="trainLogRows.length"
        shadow="never"
        class="log-viewer-card"
      >
        <template #header>
          <div class="header-row">
            <span class="card-title">{{ t('experimentAssess.trainLogViewerTitle') }}</span>
            <div class="log-actions">
              <el-input
                v-model="trainLogFilter"
                size="small"
                :placeholder="t('experimentAssess.filterLogPlaceholder')"
                clearable
                style="width: 140px"
              />
              <el-button
                size="small"
                @click="copyJson(trainLogRows)"
              >
                {{ t('experimentAssess.copyLog') }}
              </el-button>
            </div>
          </div>
        </template>
        <el-scrollbar height="220px">
          <el-table
            :data="filteredTrainLogRows"
            size="small"
            stripe
          >
            <el-table-column
              prop="epoch"
              label="Epoch"
              width="80"
            />
            <el-table-column
              prop="loss"
              label="Loss"
              width="100"
            />
            <el-table-column
              prop="eval_loss"
              label="Eval Loss"
              width="100"
            />
            <el-table-column
              prop="eval_f1"
              label="Eval F1"
              width="100"
            />
            <el-table-column
              prop="eval_accuracy"
              label="Eval Acc"
              width="100"
            />
            <el-table-column
              prop="learning_rate"
              label="LR"
              width="120"
            />
          </el-table>
        </el-scrollbar>
      </el-card>
      <el-card
        v-if="evalLogRows.length"
        shadow="never"
        class="log-viewer-card"
      >
        <template #header>
          <div class="header-row">
            <span class="card-title">{{ t('experimentAssess.evalLogViewerTitle') }}</span>
            <div class="log-actions">
              <el-input
                v-model="evalLogFilter"
                size="small"
                :placeholder="t('experimentAssess.filterLogPlaceholder')"
                clearable
                style="width: 140px"
              />
              <el-button
                size="small"
                @click="copyJson(evalLogRows)"
              >
                {{ t('experimentAssess.copyLog') }}
              </el-button>
            </div>
          </div>
        </template>
        <el-scrollbar height="220px">
          <el-table
            :data="filteredEvalLogRows"
            size="small"
            stripe
          >
            <el-table-column
              prop="split"
              label="Split"
              width="100"
            />
            <el-table-column
              prop="sample_count"
              :label="t('experimentAssess.colSampleCount')"
              width="90"
            />
            <el-table-column
              prop="accuracy"
              label="Acc"
              width="90"
            />
            <el-table-column
              prop="precision"
              label="Prec"
              width="90"
            />
            <el-table-column
              prop="recall"
              label="Recall"
              width="90"
            />
            <el-table-column
              prop="f1"
              label="F1"
              width="90"
            />
            <el-table-column
              prop="auc"
              label="AUC"
              width="90"
            />
          </el-table>
        </el-scrollbar>
      </el-card>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  summary: Record<string, unknown> | null
  confusionMatrix: { tn: number; fp: number; fn: number; tp: number } | null
  trainLogRows: Record<string, unknown>[]
  evalLogRows: Record<string, unknown>[]
}>()

const { t } = useI18n()

const trainLogFilter = ref('')
const evalLogFilter = ref('')

const filteredTrainLogRows = computed(() => {
  if (!trainLogFilter.value) return props.trainLogRows
  const keyword = trainLogFilter.value.toLowerCase()
  return props.trainLogRows.filter((row) =>
    Object.values(row).some((val) => String(val).toLowerCase().includes(keyword)),
  )
})

const filteredEvalLogRows = computed(() => {
  if (!evalLogFilter.value) return props.evalLogRows
  const keyword = evalLogFilter.value.toLowerCase()
  return props.evalLogRows.filter((row) =>
    Object.values(row).some((val) => String(val).toLowerCase().includes(keyword)),
  )
})

const copyJson = async (value: unknown) => {
  try {
    await navigator.clipboard.writeText(JSON.stringify(value, null, 2))
    ElMessage.success(t('experimentAssess.copiedToClipboard'))
  } catch {
    ElMessage.error(t('experimentAssess.copyFailed'))
  }
}
</script>

<style scoped>
.card-title {
  font-weight: 600;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.log-viewer-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}

.log-viewer-card {
  min-width: 0;
}

.log-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>

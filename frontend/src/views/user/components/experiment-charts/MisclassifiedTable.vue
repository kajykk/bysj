<template>
  <el-card
    v-if="filteredMisclassifiedRows.length"
    style="margin-top: 16px"
  >
    <template #header>
      <div class="header-row">
        <span class="card-title">{{ t('experimentAssess.misclassifiedTitle') }}</span>
        <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
          <el-select
            v-model="misclassifiedTrueLabel"
            size="small"
            clearable
            :placeholder="t('experimentAssess.trueLabelPlaceholder')"
            style="width: 110px"
          >
            <el-option
              :label="t('experimentAssess.trueLabelOption', { value: 0 })"
              :value="0"
            />
            <el-option
              :label="t('experimentAssess.trueLabelOption', { value: 1 })"
              :value="1"
            />
          </el-select>
          <el-select
            v-model="misclassifiedPredLabel"
            size="small"
            clearable
            :placeholder="t('experimentAssess.predLabelPlaceholder')"
            style="width: 110px"
          >
            <el-option
              :label="t('experimentAssess.predLabelOption', { value: 0 })"
              :value="0"
            />
            <el-option
              :label="t('experimentAssess.predLabelOption', { value: 1 })"
              :value="1"
            />
          </el-select>
          <el-select
            v-model="misclassifiedScoreRange"
            size="small"
            clearable
            :placeholder="t('experimentAssess.scoreRangePlaceholder')"
            style="width: 130px"
          >
            <el-option
              label="0.0 - 0.3"
              value="0-30"
            />
            <el-option
              label="0.3 - 0.6"
              value="30-60"
            />
            <el-option
              label="0.6 - 0.8"
              value="60-80"
            />
            <el-option
              label="0.8 - 1.0"
              value="80-100"
            />
          </el-select>
          <el-input
            v-model="misclassifiedSearchText"
            size="small"
            :placeholder="t('experimentAssess.searchPlaceholder')"
            clearable
            style="width: 180px"
          />
          <el-button
            size="small"
            type="primary"
            plain
            @click="exportSampleCsv('misclassified')"
          >
            {{ t('experimentAssess.exportCsvBtn') }}
          </el-button>
        </div>
      </div>
    </template>
    <el-table
      :data="pagedMisclassifiedRows"
      size="small"
      stripe
      max-height="320"
    >
      <el-table-column
        prop="index"
        label="#"
        width="70"
      />
      <el-table-column
        prop="true_label"
        :label="t('experimentAssess.colTrueLabel')"
        width="100"
      />
      <el-table-column
        prop="pred_label"
        :label="t('experimentAssess.colPredLabel')"
        width="100"
      />
      <el-table-column
        prop="score"
        :label="t('experimentAssess.colScore')"
        width="100"
      />
    </el-table>
    <div class="table-footer">
      <el-pagination
        v-model:current-page="misclassifiedCurrentPage"
        v-model:page-size="misclassifiedPageSize"
        small
        background
        layout="prev, pager, next, sizes, total"
        :total="filteredMisclassifiedRows.length"
        :page-sizes="[5, 10, 20]"
      />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { refDebounced } from '@/utils/debounce'
import type { PredictionSample } from './sharedChartUtils'

const { t } = useI18n()

const props = defineProps<{
  sampleRows: PredictionSample[]
  datasetName: string
}>()

// 全量样本筛选状态（保留原始逻辑，'all' 导出在模板中未使用）
const sampleSearchText = ref('')
const debouncedSampleSearch = refDebounced(sampleSearchText, 300)
const sampleCurrentPage = ref(1)
const samplePageSize = ref(5)
const sampleTrueLabel = ref<number | null>(null)
const samplePredLabel = ref<number | null>(null)
const sampleScoreRange = ref('')

// 误判样本筛选状态
const misclassifiedSearchText = ref('')
const debouncedMisclassifiedSearch = refDebounced(misclassifiedSearchText, 300)
const misclassifiedCurrentPage = ref(1)
const misclassifiedPageSize = ref(5)
const misclassifiedTrueLabel = ref<number | null>(null)
const misclassifiedPredLabel = ref<number | null>(null)
const misclassifiedScoreRange = ref('')

const csvEscape = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`
const toCsv = (rows: PredictionSample[]) => {
  const header = ['index,true_label,pred_label,score']
  const lines = rows.map(row => [row.index, row.true_label, row.pred_label, row.score].map(csvEscape).join(','))
  return [header[0], ...lines].join('\n')
}
const downloadCsv = (filename: string, csv: string) => {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const getScoreRange = (range: string): [number, number] | null => {
  if (range === '0-30') return [0, 0.3]
  if (range === '30-60') return [0.3, 0.6]
  if (range === '60-80') return [0.6, 0.8]
  if (range === '80-100') return [0.8, 1.0]
  return null
}

const filterSamples = (
  items: PredictionSample[],
  keyword: string,
  trueLabel: number | null,
  predLabel: number | null,
  scoreRange: string,
) => {
  const kw = keyword.trim().toLowerCase()
  const range = getScoreRange(scoreRange)
  return items.filter(item => {
    const hitKeyword = !kw || [item.index, item.true_label, item.pred_label, item.score].some(v => String(v).toLowerCase().includes(kw))
    const hitTrue = trueLabel === null || item.true_label === trueLabel
    const hitPred = predLabel === null || item.pred_label === predLabel
    const hitScore = !range || (item.score >= range[0] && item.score <= range[1])
    return hitKeyword && hitTrue && hitPred && hitScore
  })
}

const misclassifiedRows = computed(() => props.sampleRows.filter(item => item.true_label !== item.pred_label))
const filteredSampleRows = computed(() => filterSamples(props.sampleRows, debouncedSampleSearch.value, sampleTrueLabel.value, samplePredLabel.value, sampleScoreRange.value))
const filteredMisclassifiedRows = computed(() => filterSamples(misclassifiedRows.value, debouncedMisclassifiedSearch.value, misclassifiedTrueLabel.value, misclassifiedPredLabel.value, misclassifiedScoreRange.value))
const pagedSampleRows = computed(() => filteredSampleRows.value.slice((sampleCurrentPage.value - 1) * samplePageSize.value, sampleCurrentPage.value * samplePageSize.value))
const pagedMisclassifiedRows = computed(() => filteredMisclassifiedRows.value.slice((misclassifiedCurrentPage.value - 1) * misclassifiedPageSize.value, misclassifiedCurrentPage.value * misclassifiedPageSize.value))

const exportSampleCsv = (kind: 'all' | 'misclassified') => {
  const rows = kind === 'all' ? pagedSampleRows.value : pagedMisclassifiedRows.value
  const csv = toCsv(rows)
  downloadCsv(`${props.datasetName}_${kind}_${Date.now()}.csv`, csv)
}

watch(() => props.sampleRows, () => {
  sampleCurrentPage.value = 1
  misclassifiedCurrentPage.value = 1
})
watch([sampleSearchText, samplePageSize, sampleTrueLabel, samplePredLabel, sampleScoreRange], () => { sampleCurrentPage.value = 1 })
watch([misclassifiedSearchText, misclassifiedPageSize, misclassifiedTrueLabel, misclassifiedPredLabel, misclassifiedScoreRange], () => { misclassifiedCurrentPage.value = 1 })
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

.table-footer {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>

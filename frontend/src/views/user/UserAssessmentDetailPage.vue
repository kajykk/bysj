<template>
  <el-card>
    <template #header>
      {{ t('userAssessmentDetail.cardTitle') }}
    </template>

    <StatefulContainer
      :loading="false"
      :empty="!record"
      :empty-title="t('userAssessmentDetail.noPayloadTitle')"
      :empty-description="t('userAssessmentDetail.noPayloadDescription')"
      :show-empty-action="true"
      :empty-action-text="t('userAssessmentDetail.btnBack')"
      :empty-text="t('userAssessmentDetail.emptyText')"
      @empty-action="goBack"
    >
      <template v-if="record">
        <el-descriptions
          :column="1"
          border
        >
          <el-descriptions-item :label="t('userAssessmentDetail.labelRecordId')">
            {{ record.id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('userAssessmentDetail.labelAssessmentType')">
            {{ assessmentTypeLabel(record.type) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('userAssessmentDetail.labelScore')">
            {{ scoreText }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('userAssessmentDetail.labelRiskLevel')">
            {{ riskLevelText }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('userAssessmentDetail.labelTime')">
            {{ formatDateTime(record.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item
            v-for="field in fields"
            :key="field.label"
            :label="fieldLabel(field.label)"
          >
            {{ field.value }}
          </el-descriptions-item>
        </el-descriptions>

        <div
          v-if="fullText"
          class="text-block"
        >
          <div class="text-block__title">
            {{ t('userAssessmentDetail.fullTextTitle') }}
          </div>
          <p class="text-block__body">
            {{ fullText }}
          </p>
        </div>

        <div
          v-if="rawPayload"
          class="json-box"
        >
          <div class="json-box__title">
            {{ t('userAssessmentDetail.rawPayloadTitle') }}
          </div>
          <pre>{{ rawPayload }}</pre>
        </div>

        <div class="footer">
          <el-button @click="goBack">
            {{ t('userAssessmentDetail.btnBack') }}
          </el-button>
        </div>
      </template>
    </StatefulContainer>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import type { DataHistoryItem } from '@/api/userTypes'
import {
  NO_VALUE,
  buildDetailFields,
  extractFullText,
  extractRawPayload,
  extractRiskLevelText,
  extractScore,
} from '@/views/user/utils/assessmentHistory'
import {
  CACHE_KEY,
  decodeStatePayload,
  readCachedAssessmentItem,
} from '@/views/user/utils/assessmentDetailCache'
// P2-A 修复：复用 formatUtils 的 formatDate（别名 formatDateTime 保持模板兼容），避免本地重复定义
import { formatDate as formatDateTime } from '@/utils/formatUtils'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

/**
 * FIX-2026-10-08（ID 空间错配）：本页不再请求 `/user/risk/assessments/{id}`。
 *
 * 那个端点查的是 `risk_assessments`，而列表行的 id 来自
 * `structured_assessments` / `text_entries` / `physiological_records` ——
 * 两个独立 ID 空间。从列表点进来必然 404；万一撞上同号记录，
 * 显示的会是**另一条记录**的数据，在心理健康场景里这类串号比报错危险得多。
 *
 * 载荷来源（都不发请求）：
 *   1. history.state —— 列表跳转时随路由带过来，刷新/前进/后退都还在；
 *   2. sessionStorage 快照 —— 列表每次加载后写入当前页，新标签页打开同一链接时兜底。
 *
 * 两者都拿不到（直接粘贴 URL、跨会话分享）时 fail-closed：明确提示回列表，
 * 绝不退回那个会串号的端点。
 */
const record = ref<DataHistoryItem | null>(resolveRecord())

function readAssessmentItemFromState(): DataHistoryItem | null {
  const state = window.history.state as { assessmentItem?: unknown } | null
  // 载荷以字符串形式随路由带过来（见 encodeStatePayload），逆编码回原始项。
  return decodeStatePayload(state?.assessmentItem)
}

function resolveRecord(): DataHistoryItem | null {
  const id = Number(route.params.id)
  if (!Number.isFinite(id)) return null
  const candidate =
    readAssessmentItemFromState() ?? readCachedAssessmentItem(CACHE_KEY, id)
  if (!candidate) return null
  // id 必须与路由一致：否则宁可什么都不显示，也不显示别人的记录。
  if (Number(candidate.id) !== id) return null
  if (typeof candidate.data !== 'object' || candidate.data === null) {
    return { ...candidate, data: {} }
  }
  return candidate
}

const fields = computed(() => (record.value ? buildDetailFields(record.value) : []))
const fullText = computed(() => (record.value ? extractFullText(record.value) : ''))
const rawPayload = computed(() => (record.value ? extractRawPayload(record.value) : ''))
const scoreText = computed(() => {
  if (!record.value) return NO_VALUE
  const score = extractScore(record.value)
  return score === null ? NO_VALUE : String(score)
})
const riskLevelText = computed(() =>
  record.value ? extractRiskLevelText(record.value) : NO_VALUE
)

const TYPE_LABEL_KEYS: Record<string, string> = {
  structured: 'typeStructured',
  text: 'typeText',
  physiological: 'typePhysiological',
  record: 'typeRecord',
}
const assessmentTypeLabel = (value?: string) => {
  const key = TYPE_LABEL_KEYS[value || '']
  return key ? t(`userAssessmentDetail.${key}`) : value || NO_VALUE
}

/** 载荷键 → i18n 键。未登记的键让 vue-i18n 回落到键名本身，不会漏出 undefined。 */
const fieldLabel = (key: string) => t(`userAssessmentDetail.field.${key}`)

// ISS-056 修复：改用 router.back()，避免透传全部 query（可能包含 token 等敏感参数）
// 无历史记录时回退到评估列表页
const goBack = () => {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/user/assessments')
  }
}
</script>

<style scoped>
.footer {
  margin-top: 12px;
}

.text-block {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid var(--border-lighter);
  border-radius: var(--radius-large);
  background: var(--bg-page);
}

.text-block__title {
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--text-primary);
}

.text-block__body {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
}

.json-box {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid var(--border-lighter);
  border-radius: var(--radius-large);
  background: var(--bg-page);
}

.json-box__title {
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--text-primary);
}

pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: var(--font-size-extra-small);
}
</style>
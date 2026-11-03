<template>
  <el-alert
    v-if="scope"
    class="population-scope"
    type="info"
    :closable="false"
    show-icon
  >
    <template #title>
      <span>{{ t('populationScope.title') }}</span>
      <el-tag
        class="scope-tag"
        size="small"
        type="warning"
        effect="plain"
      >
        {{ evidenceLabel }}
      </el-tag>
      <el-tag
        v-if="!scope.automated_decision_allowed"
        class="scope-tag"
        size="small"
        type="danger"
        effect="plain"
      >
        {{ t('populationScope.autoDecisionDisabled') }}
      </el-tag>
    </template>
    <div class="scope-body">
      <p>
        <strong>{{ t('populationScope.populationLabel') }}</strong>{{ scope.population_label }}
      </p>
      <p>
        <strong>{{ t('populationScope.labelDefinitionLabel') }}</strong>{{ scope.label_definition }}
      </p>
      <p>
        <strong>{{ t('populationScope.validationLabel') }}</strong>{{ scope.validation_cohort }}
      </p>
      <p>
        <strong>{{ t('populationScope.intendedUseLabel') }}</strong>{{ scope.intended_use }}
      </p>
      <p v-if="scope.out_of_scope?.length">
        <strong>{{ t('populationScope.outOfScopeLabel') }}</strong>{{ scope.out_of_scope.join('；') }}
      </p>
      <p v-if="scope.abstention_recommended">
        <strong>{{ t('populationScope.abstentionLabel') }}</strong>{{ abstentionText }}
      </p>
      <p v-else>
        <strong>{{ t('populationScope.disclosureLabel') }}</strong>{{ scope.disclosure }}
      </p>
    </div>
  </el-alert>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PopulationScope } from '@/api/modelApi'

const props = defineProps<{
  scope?: PopulationScope | null
}>()

const { t, te } = useI18n()

const EVIDENCE_I18N_KEYS: Record<string, string> = {
  internal_source_split: 'internalSourceSplit',
  groupwise_oof: 'groupwiseOof',
  cross_source: 'crossSource',
  small_internal_split: 'smallInternalSplit',
  small_external: 'smallExternal',
  synthetic_label_derived: 'syntheticLabelDerived',
  not_evaluable: 'notEvaluable',
  heuristic_fallback: 'heuristicFallback',
}

const evidenceLabel = computed(() => {
  if (!props.scope) return ''
  const i18nKey = EVIDENCE_I18N_KEYS[props.scope.evidence_level]
  return i18nKey && te(`populationScope.evidence.${i18nKey}`)
    ? t(`populationScope.evidence.${i18nKey}`)
    : props.scope.evidence_level
})

const abstentionText = computed(() => {
  const scope = props.scope
  if (!scope) return ''
  return scope.abstention_reasons?.length
    ? scope.abstention_reasons.join('；')
    : scope.disclosure
})
</script>

<style scoped>
.population-scope {
  margin-bottom: 12px;
}

.scope-tag {
  margin-left: 8px;
}

.scope-body p {
  margin: 4px 0;
  line-height: 1.55;
}
</style>

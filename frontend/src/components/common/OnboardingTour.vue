<template>
  <el-tour
    v-model="isOpen"
    :current="currentStep"
    @finish="onTourComplete"
    @close="onTourCancel"
  >
    <el-tour-step
      v-for="(step, index) in steps"
      :key="index"
      :target="step.target"
      :title="step.title"
      :description="step.description"
      :placement="step.placement"
    />
  </el-tour>
</template>

<script setup lang="ts">
import { useOnboarding } from '@/composables/useOnboarding'

const props = defineProps<{
  role: string
}>()

const {
  isOpen,
  currentStep,
  onTourComplete,
  onTourCancel,
  steps,
} = useOnboarding(props.role)

defineExpose({
  tryStartOnboarding: () => useOnboarding(props.role).tryStartOnboarding(),
  restartTour: () => useOnboarding(props.role).restartTour(),
})
</script>

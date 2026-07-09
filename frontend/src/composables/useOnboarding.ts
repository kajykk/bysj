import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const ONBOARDING_STORAGE_KEY = 'dws:onboarding:completed'
const ONBOARDING_VERSION = 'v1'

export interface OnboardingStep {
  target: string
  title: string
  description: string
  placement?: 'top' | 'bottom' | 'left' | 'right'
  showArrow?: boolean
}

const isOpen = ref(false)
const currentStep = ref(0)

function getStorageKey(role: string): string {
  return `${ONBOARDING_STORAGE_KEY}:${role}:${ONBOARDING_VERSION}`
}

function isOnboardingCompleted(role: string): boolean {
  try {
    return localStorage.getItem(getStorageKey(role)) === 'true'
  } catch {
    return false
  }
}

function markOnboardingCompleted(role: string): void {
  try {
    localStorage.setItem(getStorageKey(role), 'true')
  } catch {
    // localStorage 不可用时静默失败
  }
}

function clearOnboardingCompleted(role: string): void {
  try {
    localStorage.removeItem(getStorageKey(role))
  } catch {
    // localStorage 不可用时静默失败
  }
}

export function useOnboarding(role: string) {
  const { t } = useI18n()

  const steps = computed(() => getSteps(role, t))

  function startTour() {
    if (!steps.value.length) return
    currentStep.value = 0
    isOpen.value = true
  }

  function tryStartOnboarding() {
    if (!isOnboardingCompleted(role)) {
      startTour()
    }
  }

  function restartTour() {
    clearOnboardingCompleted(role)
    startTour()
  }

  function onTourComplete() {
    markOnboardingCompleted(role)
    isOpen.value = false
  }

  function onTourCancel() {
    markOnboardingCompleted(role)
    isOpen.value = false
  }

  return {
    isOpen,
    currentStep,
    startTour,
    tryStartOnboarding,
    restartTour,
    onTourComplete,
    onTourCancel,
    steps,
  }
}

function getSteps(role: string, t: (key: string) => string): OnboardingStep[] {
  switch (role) {
    case 'user':
      return getUserSteps(t)
    case 'counselor':
      return getCounselorSteps(t)
    case 'admin':
      return getAdminSteps(t)
    default:
      return []
  }
}

function getUserSteps(t: (key: string) => string): OnboardingStep[] {
  return [
    {
      target: '.layout-aside',
      title: t('onboarding.steps.user.navMenuTitle'),
      description: t('onboarding.steps.user.navMenuDesc'),
      placement: 'right',
    },
    {
      target: '.warning-badge',
      title: t('onboarding.steps.user.warningBadgeTitle'),
      description: t('onboarding.steps.user.warningBadgeDesc'),
      placement: 'bottom',
    },
    {
      target: '[data-tour="user-dashboard"]',
      title: t('onboarding.steps.user.dashboardTitle'),
      description: t('onboarding.steps.user.dashboardDesc'),
      placement: 'right',
    },
    {
      target: '[data-tour="user-risk"]',
      title: t('onboarding.steps.user.riskAssessTitle'),
      description: t('onboarding.steps.user.riskAssessDesc'),
      placement: 'right',
    },
    {
      target: '[data-tour="user-warnings"]',
      title: t('onboarding.steps.user.warningsTitle'),
      description: t('onboarding.steps.user.warningsDesc'),
      placement: 'right',
    },
  ]
}

function getCounselorSteps(t: (key: string) => string): OnboardingStep[] {
  return [
    {
      target: '.layout-aside',
      title: t('onboarding.steps.counselor.navMenuTitle'),
      description: t('onboarding.steps.counselor.navMenuDesc'),
      placement: 'right',
    },
    {
      target: '.warning-badge',
      title: t('onboarding.steps.counselor.warningBadgeTitle'),
      description: t('onboarding.steps.counselor.warningBadgeDesc'),
      placement: 'bottom',
    },
    {
      target: '[data-tour="counselor-warnings"]',
      title: t('onboarding.steps.counselor.warningMgmtTitle'),
      description: t('onboarding.steps.counselor.warningMgmtDesc'),
      placement: 'right',
    },
    {
      target: '[data-tour="counselor-users"]',
      title: t('onboarding.steps.counselor.userMgmtTitle'),
      description: t('onboarding.steps.counselor.userMgmtDesc'),
      placement: 'right',
    },
  ]
}

function getAdminSteps(t: (key: string) => string): OnboardingStep[] {
  return [
    {
      target: '.layout-aside',
      title: t('onboarding.steps.admin.navMenuTitle'),
      description: t('onboarding.steps.admin.navMenuDesc'),
      placement: 'right',
    },
    {
      target: '.warning-badge',
      title: t('onboarding.steps.admin.warningBadgeTitle'),
      description: t('onboarding.steps.admin.warningBadgeDesc'),
      placement: 'bottom',
    },
    {
      target: '[data-tour="admin-dashboard"]',
      title: t('onboarding.steps.admin.dashboardTitle'),
      description: t('onboarding.steps.admin.dashboardDesc'),
      placement: 'right',
    },
    {
      target: '[data-tour="admin-observability"]',
      title: t('onboarding.steps.admin.observabilityTitle'),
      description: t('onboarding.steps.admin.observabilityDesc'),
      placement: 'right',
    },
  ]
}

// 供测试使用
export function resetOnboardingState() {
  isOpen.value = false
  currentStep.value = 0
}

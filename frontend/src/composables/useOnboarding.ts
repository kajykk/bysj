import { ref } from 'vue'

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
  function startTour() {
    if (!getSteps(role).length) return
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
    steps: getSteps(role),
  }
}

function getSteps(role: string): OnboardingStep[] {
  switch (role) {
    case 'user':
      return getUserSteps()
    case 'counselor':
      return getCounselorSteps()
    case 'admin':
      return getAdminSteps()
    default:
      return []
  }
}

function getUserSteps(): OnboardingStep[] {
  return [
    {
      target: '.layout-aside',
      title: '导航菜单',
      description: '这里是你的主要导航菜单，可以在这里访问所有功能页面。',
      placement: 'right',
    },
    {
      target: '.warning-badge',
      title: '告警通知',
      description: '当有新的风险告警时，这里会显示红点提示，点击可查看详情。',
      placement: 'bottom',
    },
    {
      target: '[data-tour="user-dashboard"]',
      title: '仪表盘',
      description: '仪表盘展示你的风险评估概览和趋势数据，建议定期查看。',
      placement: 'right',
    },
    {
      target: '[data-tour="user-risk"]',
      title: '风险评估',
      description: '在这里进行心理健康风险评估，系统会根据你的回答生成个性化报告。',
      placement: 'right',
    },
    {
      target: '[data-tour="user-warnings"]',
      title: '告警中心',
      description: '查看你的历史告警记录和干预建议。',
      placement: 'right',
    },
  ]
}

function getCounselorSteps(): OnboardingStep[] {
  return [
    {
      target: '.layout-aside',
      title: '咨询师导航',
      description: '在这里管理你负责的用户、查看告警和审核评估。',
      placement: 'right',
    },
    {
      target: '.warning-badge',
      title: '告警通知',
      description: '当你的用户出现高风险时，这里会实时推送告警通知。',
      placement: 'bottom',
    },
    {
      target: '[data-tour="counselor-warnings"]',
      title: '告警管理',
      description: '查看和处理所有用户告警，及时跟进高风险用户。',
      placement: 'right',
    },
    {
      target: '[data-tour="counselor-users"]',
      title: '用户管理',
      description: '查看你负责的用户列表和他们的风险评估历史。',
      placement: 'right',
    },
  ]
}

function getAdminSteps(): OnboardingStep[] {
  return [
    {
      target: '.layout-aside',
      title: '管理员导航',
      description: '在这里管理系统配置、模板、告警和可观测性。',
      placement: 'right',
    },
    {
      target: '.warning-badge',
      title: '告警通知',
      description: '系统级告警会在这里实时推送，请及时关注。',
      placement: 'bottom',
    },
    {
      target: '[data-tour="admin-dashboard"]',
      title: '系统仪表盘',
      description: '查看系统整体运行状态、用户统计和风险分布。',
      placement: 'right',
    },
    {
      target: '[data-tour="admin-observability"]',
      title: '可观测性',
      description: '监控系统指标、日志和链路追踪数据。',
      placement: 'right',
    },
  ]
}

// 供测试使用
export function resetOnboardingState() {
  isOpen.value = false
  currentStep.value = 0
}

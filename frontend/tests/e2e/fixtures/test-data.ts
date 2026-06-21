/**
 * Test data fixtures for E2E tests
 */

export const TEST_USERS = {
  valid: {
    email: 'test@example.com',
    password: 'TestPassword123',
    name: 'Test User',
  },
  invalid: {
    email: 'invalid-email',
    password: '123',
  },
  admin: {
    email: 'admin@example.com',
    password: 'AdminPassword123',
  },
}

export const STRUCTURED_DATA = {
  valid: {
    sleepHours: 7.5,
    exerciseMinutes: 45,
    heartRate: 72,
    steps: 8000,
  },
  highRisk: {
    sleepHours: 3.0,
    exerciseMinutes: 0,
    heartRate: 95,
    steps: 1000,
  },
  lowRisk: {
    sleepHours: 8.0,
    exerciseMinutes: 60,
    heartRate: 65,
    steps: 12000,
  },
}

export const TEXT_INPUTS = {
  valid: 'I feel very anxious and stressed about work',
  short: 'I am sad',
  long: 'I feel extremely depressed and hopeless. I cannot sleep at night and have no appetite. Everything seems pointless and I do not see any reason to continue.',
  empty: '',
}

export const PHYSIOLOGICAL_DATA = {
  valid: {
    sleepHours: 7.0,
    exerciseMinutes: 30,
    heartRate: 70,
    steps: 6000,
  },
}

export const FUSION_DATA = {
  valid: {
    text: 'I feel very anxious today',
    structured: {
      sleepHours: 5.0,
      exerciseMinutes: 10,
    },
  },
}

export const DATE_RANGES = {
  valid: {
    start: '2024-01-01',
    end: '2024-12-31',
  },
  invalid: {
    start: 'invalid',
    end: 'invalid',
  },
}

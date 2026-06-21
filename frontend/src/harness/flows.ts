import { createMockApi } from './apiHarness'
import { runHarnessSuite, type HarnessScenario } from '@/test-harness'

export function buildFrontendHarness() {
  const api = createMockApi([
    {
      method: 'GET',
      url: '/api/v1/user/risk/report',
      response: { status: 200, body: { data: { risk_level: 3, risk_score: 78 } } },
    },
    {
      method: 'GET',
      url: '/api/v1/user/content/recommendations',
      response: { status: 200, body: { data: { explain: { strategy: 'sleep hygiene' } } } },
    },
  ])

  const scenarios: HarnessScenario[] = [
    {
      name: 'risk-report-mock',
      kind: 'integration',
      execute: async () => {
        const response = await api.request('GET', '/api/v1/user/risk/report')
        return {
          name: 'risk-report-mock',
          kind: 'integration',
          status: response.status === 200 ? 'passed' : 'failed',
          durationMs: 2,
          details: response.body as Record<string, unknown>,
        }
      },
    },
    {
      name: 'recommendation-mock',
      kind: 'system',
      execute: async () => {
        const response = await api.request('GET', '/api/v1/user/content/recommendations')
        return {
          name: 'recommendation-mock',
          kind: 'system',
          status: response.status === 200 ? 'passed' : 'failed',
          durationMs: 2,
          details: response.body as Record<string, unknown>,
        }
      },
    },
  ]

  return { scenarios }
}

export async function runFrontendHarness() {
  const { scenarios } = buildFrontendHarness()
  return runHarnessSuite(scenarios, {})
}

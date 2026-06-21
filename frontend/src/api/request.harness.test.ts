import { describe, expect, it } from 'vitest'
import { runHarnessSuite } from '@/test-harness'

const makeScenario = (name: string, status: 'passed' | 'failed') => ({
  name,
  kind: 'integration' as const,
  execute: async () => ({
    name,
    kind: 'integration' as const,
    status,
    durationMs: 1,
    details: { endpoint: '/api/v1/mock' },
  }),
})

describe('frontend harness coverage', () => {
  it('collects harness results for integration-style flows', async () => {
    const run = await runHarnessSuite([makeScenario('request-success', 'passed')], {})
    expect(run.passed).toBe(true)
    expect(run.results).toHaveLength(1)
  })

  it('marks the suite failed when any scenario fails', async () => {
    const run = await runHarnessSuite([
      makeScenario('request-success', 'passed'),
      makeScenario('request-failure', 'failed'),
    ], {})
    expect(run.passed).toBe(false)
  })
})

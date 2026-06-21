export type HarnessStatus = 'passed' | 'failed'

export interface HarnessResult {
  name: string
  kind: 'unit' | 'integration' | 'system'
  status: HarnessStatus
  durationMs: number
  details?: Record<string, unknown>
  error?: string
}

export interface HarnessScenario<TContext = Record<string, unknown>> {
  name: string
  kind: HarnessResult['kind']
  setup?: (context: TContext) => Promise<void> | void
  execute: (context: TContext) => Promise<HarnessResult> | HarnessResult
  teardown?: (context: TContext) => Promise<void> | void
}

export async function runHarnessSuite<TContext extends Record<string, unknown>>(
  scenarios: HarnessScenario<TContext>[],
  baseContext: TContext,
) {
  const results: HarnessResult[] = []

  for (const scenario of scenarios) {
    const context = { ...baseContext }
    const startedAt = performance.now()

    try {
      await scenario.setup?.(context)
      const result = await scenario.execute(context)
      results.push({
        ...result,
        durationMs: result.durationMs ?? performance.now() - startedAt,
      })
    } catch (error) {
      results.push({
        name: scenario.name,
        kind: scenario.kind,
        status: 'failed',
        durationMs: performance.now() - startedAt,
        error: error instanceof Error ? error.message : String(error),
      })
    } finally {
      await scenario.teardown?.(context)
    }
  }

  return {
    passed: results.every((result) => result.status === 'passed'),
    results,
  }
}

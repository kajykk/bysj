import { describe, expect, it } from 'vitest'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { runFrontendHarness } from './flows'
import { createHarnessReport, normalizeHarnessResult, writeHarnessReport } from './report'

const currentDir = dirname(fileURLToPath(import.meta.url))
const reportPath = resolve(currentDir, '../../test-results/harness-report.vitest.json')

describe('frontend harness flows', () => {
  it('runs mocked API scenarios and emits normalized harness report json', async () => {
    let run: Awaited<ReturnType<typeof runFrontendHarness>> | null = null

    try {
      run = await runFrontendHarness()
      expect(run.passed).toBe(true)
      expect(run.results).toHaveLength(2)
      expect(run.results[0].details?.data ?? run.results[0].details).toBeTruthy()
    } finally {
      const report = createHarnessReport({
        source: 'vitest',
        passed: run?.passed ?? false,
        scenarioCount: run?.results.length ?? 0,
        results: (run?.results ?? []).map((item) =>
          normalizeHarnessResult({
            name: item.name,
            kind: item.kind,
            status: item.status,
            durationMs: item.durationMs,
            details: item.details,
            error: item.error,
          }),
        ),
        meta: {
          runner: 'vitest',
          framework: 'vitest',
          version: '1.0',
        },
      })
      writeHarnessReport(reportPath, report)
    }
  })
})

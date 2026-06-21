import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'

export type HarnessKind = 'unit' | 'integration' | 'system'
export type HarnessStatus = 'passed' | 'failed'
export type HarnessSource = 'vitest' | 'playwright'

export interface HarnessReportResult {
  name: string
  kind: HarnessKind
  status: HarnessStatus
  durationMs: number
  details: Record<string, unknown>
  error: string | null
}

export function attachReportLinks(result: HarnessReportResult, links: Record<string, string>): HarnessReportResult {
  return {
    ...result,
    details: {
      ...result.details,
      links,
    },
  }
}

export interface HarnessReportMeta {
  runner: HarnessSource
  framework: string
  version: string
}

export interface HarnessReport {
  source: HarnessSource
  generatedAt: string
  passed: boolean
  scenarioCount: number
  results: HarnessReportResult[]
  meta: HarnessReportMeta
}

export function normalizeHarnessResult(
  result: Partial<HarnessReportResult> & Pick<HarnessReportResult, 'name' | 'kind' | 'status' | 'durationMs'>,
): HarnessReportResult {
  return {
    ...result,
    details: result.details ?? {},
    error: result.error ?? null,
  }
}

export function createHarnessReport(params: Omit<HarnessReport, 'generatedAt'> & { generatedAt?: string }): HarnessReport {
  return {
    ...params,
    generatedAt: params.generatedAt ?? new Date().toISOString(),
  }
}

export function writeHarnessReport(path: string, report: HarnessReport) {
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, JSON.stringify(report, null, 2), 'utf-8')
}

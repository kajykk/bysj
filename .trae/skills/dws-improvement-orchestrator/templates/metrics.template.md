# DWS Improvement — Metrics

## Metric Definitions

| Metric | Numerator X | Denominator Y | Source |
|---|---|---|---|
| P0 open count | 状态非 Closed 的 P0 任务数 | 全部 P0 任务数 | backlog.md |
| P1 fix rate | Closed 的 P1 任务数 | 全部 P1 任务数 | backlog.md |
| Crisis pass rate | 通过的危机链路测试数 | 全部危机链路测试数 | reports/crisis-chain-report.md |
| E2E pass rate | 通过的 E2E 用例数 | 全部 E2E 用例数 | reports/e2e-report.md |
| Event coverage | 已实现埋点事件数 | 计划埋点事件数 | pilot/event-tracking.md |

## Current Snapshot

| Metric | X | Y | Percent | Source | Updated At |
|---|---:|---:|---:|---|---|

## Gate Metrics

| Gate | Required Metric | Current | Pass |
|---|---|---|---|

## Notes

P1 fix rate uses live backlog stats; new P1 enters the denominator. All open P1 default-block M2 unless waived in decisions.md.

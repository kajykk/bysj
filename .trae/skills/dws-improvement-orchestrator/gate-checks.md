# Gate Checks (M0-M6)

`确认阶段` checks in order: automatic checks → manual confirmations filled → evidence exists.

## Automatic vs manual gates

| Transition | Automatic checks | Manual confirmation |
|---|---|---|
| PHASE_0_INIT → PHASE_1_SECURITY (M0) | backlog/acceptance-criteria/STATE.md exist; test-account field non-empty | 产品负责人确认范围冻结 |
| PHASE_1_SECURITY → PHASE_2_UX (M1) | P0 open count==0; `reports/crisis-chain-report.md` exists and pass rate==100% | 心理专家确认危机提示文案 |
| PHASE_2_UX → PHASE_3_WORKBENCH (M2) | P1 fix rate ≥85% (auto-computed) | 产品+测试确认核心流程可用 |
| PHASE_3_WORKBENCH → PHASE_4_DATA_PILOT (M3) | three-role key-path E2E passes | 产品确认体验达标 |
| PHASE_4_DATA_PILOT → PHASE_5_VERIFICATION (M4) | 7 files under `pilot/` exist: `event-tracking.md`, `interview-guide.md`, `questionnaire.md`, `privacy-notice.md`, `pilot-plan.md`, `deployment-guide.md`, `rollback-plan.md`; event coverage==100% | 心理专家审核问卷/访谈提纲 |
| PHASE_5_VERIFICATION → PHASE_6_DELIVERY (M5) | E2E/performance/security/a11y reports exist and meet targets | 测试负责人签字 |
| PHASE_6_DELIVERY → CLOSED (M6) | pilot-version tag / deployment handbook / retrospective report exist | 干系人确认交付 |

The orchestrator does not pretend to judge material quality; manual items must be explicitly confirmed before advancing.

## Evidence field check rule

Evidence may be a file path, report path, test-command record, screenshot path, or meeting-notes link. If Evidence looks like a local path, the orchestrator checks the file exists; if it is text or an external link, only check non-empty and require manual confirmation.

## Waiver rules

**Non-waivable gates** (不可豁免):
- P0 open count must be 0 for PHASE_1_SECURITY → PHASE_2_UX and all later transitions.
- Crisis chain pass rate must be 100% for PHASE_1_SECURITY → PHASE_2_UX.
- Core E2E must pass before PHASE_6_DELIVERY.
- Missing STATE.md/backlog.md/acceptance-criteria.md cannot be waived.

**Waivable gates** (须 decisions.md 记录):
- P1 fix rate below 85%: waivable only with a decision record.
- Missing non-critical pilot material: waivable only before PHASE_5_VERIFICATION, not before CLOSED.
- A11Y/performance non-blocking gaps: waivable if documented with owner and deadline.

`decisions.md` must not become a backdoor to arbitrarily skip quality gates. All open P1 default-blocks M2 unless waived in `decisions.md`; phase-unrelated new P1 must also be waived or they count toward M2.

## P1 fix-rate statistics

P1 fix rate = Closed P1 tasks / all P1 tasks, computed live from `backlog.md`. New P1 enters the denominator. All open P1 default-block M2 unless waived in `decisions.md`.

## Self-test protocol (document state-machine test, v1 — no scripts)

1. Create mock `STATE.md` / `backlog.md`.
2. Mark PHASE_0_INIT gate checks satisfied (automatic items + simulated manual confirmation).
3. Run `确认阶段` → verify state changes to `PHASE_1_SECURITY`.
4. Repeat through `PHASE_6_DELIVERY`.
5. Verify final state becomes `CLOSED`.
6. **Counterexample A**: with P0 not cleared, `确认阶段` for PHASE_1_SECURITY → PHASE_2_UX must be rejected with a reason.
7. **Counterexample B**: when a Required skill in dispatch-registry is missing, `派发任务` must NOT fail; it enters `manual-mode` and records in `STATE.md`: missing skill / affected WP / substitute / blocking status.
8. **Counterexample C**: at PHASE_1_SECURITY → PHASE_2_UX, if `manual_confirmations` M1 (心理专家确认) is unfilled, `确认阶段` must be rejected and prompt the pending manual item.

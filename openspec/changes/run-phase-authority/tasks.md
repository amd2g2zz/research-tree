## 1. Tests (RED first)

- [x] 1.1 RED: tests/test_run_phase_authority.py collection fails without the module API (RunPhaseStore, build_phase_snapshot, advance_phase missing)
- [x] 1.2 GREEN: 13/13 scenarios pass

## 2. Implementation

- [x] 2.1 RunPhaseStore: digest-checked state JSON, append-only event log, announce cursor (tree_state.py)
- [x] 2.2 CanonicalResearchTreeStateService.advance_phase: gate-enforced phase writer
- [x] 2.3 Writers: handoff compile (birth compiled + research after confirm), coordinator owner events (handoff_confirmed/all_slots_closed/readiness_passed), reopen_alignment
- [x] 2.4 Hook: store-first resolution, tail snapshot line, exactly-once event announcement
- [x] 2.5 alignment_graph plan()/record() entry refusal under research (redirect, no turn consumed)

## 3. Gate

- [ ] 3.1 full suite + ruff + delivery workflow + openspec governance + skill package check -> PR fix/issue-530-run-phase-authority -> dev

# Proposal: best-of-n

## Why

issue #334 (confirmed by reconciliation): requester-stated product
attribute 8 — "best-of-N" — is unimplemented. Policy.py is a deterministic
single-path selector; no alternative candidates are generated or compared.

## What Changes

NEW `src/research_tree/best_of_n.py`:
- `Candidate` frozen dataclass: id, kind, method, score, basis_refs, rationale.
- `CandidatePool` with `require_method_independence` validation (duplicates rejected).
- `CandidateSelection`: selected_id/method/score/rationale + persistence_payload + human_brief_summary.
- `select_candidate(pool, tie_break="deterministic")`: highest-score + deterministic tie-break.
- `close_p0_slot_with_single_candidate(...)`: P0 slots must have ≥2 candidates OR explicit `degradation_recorded=True`; P2 slots allow single candidate.

## Impact

- src/research_tree/best_of_n.py (new) — no behavior change to existing modules.
- Coordinates with #333 (policy already exposed) — Decision Slot closures may
  invoke select_candidate.

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| P0 single-candidate without record raises | test_p0_slot_closed_with_single_candidate_without_record_raises |
| P0 single-candidate with record succeeds | test_p0_slot_closed_with_single_candidate_when_recorded_succeeds |
| Non-P0 allows single candidate | test_non_p0_slot_allows_single_candidate |
| highest score + rationale selected | test_select_candidate_picks_highest_score_with_rationale |
| method independence validated | test_candidate_pool_requires_diversity_when_independence_declared |
| persistence payload recorded | test_select_candidate_records_persistence_payload |
| Human Brief surfaces N candidates + winning rationale | test_human_brief_summary_records_n_and_reason |

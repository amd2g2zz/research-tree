# Design: risk-scaled-gates

## Context

`evaluate_research_stop` recomputes every slot's blocker list on each
evaluation pass. Today all six named blockers are unconditional, so a P2
"which blog post do we cite" slot pays the identical gauntlet as a P0
"which architecture do we ship" slot. The `priority` field already exists on
every compiled slot and already gates `validation_required` — this change
extends that precedent to the blocker set instead of inventing a new
risk-tier field.

## Goals / Non-Goals

- Goals: blocker subsets scale by slot priority; config constants scale by a
  task profile; the never-scaling gate list is written down and pinned by a
  test.
- Non-Goals: auto-closing slots without coordinator involvement (the
  coordinator still owns the actual `status: closed` transition, exactly as
  today); changing ranking, `validation_required`, or any #494/#495 producer;
  reusing the coordinator-level `p0_closure_tokens` obligation (a separate,
  unaffected mechanism).

## Decisions

### D1 — Subset selection filters produced blockers (producers stay intact)

`evaluate_research_stop` keeps computing `shallow_refs`, `mechanism_missing`,
and open-frontier counts unconditionally, and `_ensure_mechanism_drilldown`
keeps scheduling mandatory drill-downs for every landscape slot. The subset
selection only decides which of the produced blockers attach to the slot's
`closure_blockers`. This keeps the #494/#495 machinery bit-identical and the
diff confined to the gate attachment step.

### D2 — Priority subsets

- P0: full set — coordinator assessment, evidence floor, validation oracle,
  shallow source depth, mechanism artifacts, frontier remnants.
- P1: coordinator assessment, evidence floor, validation oracle. A P1 slot
  opts back into the landscape-depth, mechanism, and coverage gates with
  `landscape_gates: true` (compiled into the slot next to
  `landscape_required`, which continues to control only the producer side).
- P2: evidence floor, validation oracle only.

The coordinator-assessment blocker fires when the slot's own subset gates are
satisfied (evidence floor met, oracle passed where required, and — for P0 or
P1-opted-in — no shallow sources, no missing mechanisms, no open frontier
actions). For P1/P2 the coverage and landscape conditions leave candidacy
unchanged; for P2 the assessment blocker itself is not in the subset, so a
satisfied P2 slot presents an empty `closure_blockers` list and the
coordinator can close it directly. `evaluate_research_stop` never sets
`status: closed` itself — that authority transition is unchanged for every
priority.

### D3 — Config profile

`RecursiveSearchConfig` gains `profile: small|standard|deep` (default
`standard`) and `minimum_evidence`. The three profiled fields
(`minimum_evidence`, `max_depth`, `transition_budget`) use an unset sentinel
default so a profile fills exactly the fields the caller did not pass;
explicit arguments always win, and `RecursiveSearchConfig(**asdict(cfg))`
round-trips idempotently. Defaults (documented, pinned by tests):

| profile   | minimum_evidence | max_depth | transition_budget |
| --------- | ---------------- | --------- | ----------------- |
| small     | 1                | 3         | 16                |
| standard  | 2 (today)        | 5 (today) | 64 (today)        |
| deep      | 3                | 8         | 128               |

The evidence floor flows through `_slot_has_minimum_evidence` and the
closure-deficit helpers as an explicit parameter defaulting to today's
`_MINIMUM_EVIDENCE = 2`, so `standard` is behavior-identical and legacy
callers keep compiling.

### D4 — ADR: gates that never scale

The irreversible/authority/forgery gates ignore slot priority permanently:

1. **Authority fingerprint** — `independent_review.py` binds every
   independent verification to a SHA-256 authority fingerprint; a P2 slot
   cannot weaken or skip it.
2. **Phase transitions** — `tree_state.py` `TREE_PHASE_TRANSITIONS` gates the
   phase graph for the whole tree; priorities do not enter it.
3. **Digest binding** — the deliverable-quality review binds to the exact
   report bytes (`manifest_digests`); a P2 tree's stale review is rejected
   exactly like a P0 one.
4. **Evidence strict mode** — Finding Packs backing closure assessments and
   decisions must carry strict, content-bound evidence
   (`evidence_mode: "strict"`, canonical `EvidenceAnchor`s); no priority
   relaxes it.

Quality/coverage gates (source depth, mechanism artifacts, frontier
coverage) are the ones that scale with risk.

## Risks / Trade-offs

- Default-priority slots compile as P1, so hand-built or legacy slots without
  an explicit priority now get the middle set instead of the full set. The
  full suite stays green because every blocker-string pin in the repo uses
  P0 slots; the P0 set is regression-pinned in this change's tests.
- A P1 slot with open frontier actions may already present the coordinator
  assessment blocker (coverage is not in its subset) — the run itself stays
  `searching` while any frontier action remains, and the coordinator owns the
  close decision.
- `[risk: LOW]` per GitNexus impact (8 impacted symbols, epistemic exact);
  direct callers are `initialize_research_state` and
  `apply_research_results`.

## Migration Plan

Additive fields only; no persisted-state migration. Legacy state payloads
without `profile`/`minimum_evidence` in `config` reconstruct with the
standard defaults, and slots without `landscape_gates` keep the
priority-derived subset.

## Open Questions

- None blocking; profile magnitudes are pinned by tests and can be tuned by
  editing the profile table plus its test in one commit.

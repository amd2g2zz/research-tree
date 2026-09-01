# Proposal: human-brief-operating-model

## Why

Senior-user evaluation #292 named the gap: "Human Brief is not yet an
operating model" — it explains contracts and evidence well but lacks team
capacity, owner roles, SLA, concurrent-project limits, meeting replacement,
and adoption metrics (gate 8 pre-work, issue #452). The delivery template and
the compiled Human Brief prioritize technical/governance content over
operating cadence.

The runtime already holds the data the operator view needs: the confirmed
StrategyProjection, per-oracle `goal_satisfaction` registrations (#429),
goal-contribution assessments, and the coordinator's `why_not_complete`
resolve entries. The compiled Human Brief never surfaced them.

## What Changes

- `assets/human-brief-template.md` restructures around the seven
  operating-model fields: Roles, SLA, Concurrency limits, Blockers, Outcome
  layers, Adoption metrics, Fallback plan. Runtime-fed fields (Blockers,
  Outcome layers) annotate their real artifact sources; SLA, Concurrency
  limits, and Adoption metrics are baseline-run dimensions — fields present,
  values labeled as measured baselines, never commitments. Pre-existing
  semantic sections (Alignment Trace, next visible milestone + validation
  oracle, decision gate) are preserved.
- `src/research_tree/delivery.py` adds an `operating_model` block to the
  compiled Human Brief document with an exact-key schema (schema 1):
  - `roles` — the three operating roles with responsibilities and handoff
    surfaces (structural contract, aligned with the closed origin vocabulary
    wording from #449).
  - `outcome_layers` — confirmed projection (id, revision, display digest,
    #450 authority fingerprint), current per-oracle `goal_satisfaction`
    verdicts, and per-slot goal-contribution summaries (latest per finding
    pack), all read from the run's own artifacts.
  - `blockers` — mirrors the coordinator's `why_not_complete` resolve entries
    verbatim, each with an owner role (acceptance obligations route to the
    human requester; the rest to the research owner). When the coordinator
    has no state for the run, the blocker list says so explicitly
    (`coordinator_state`) instead of claiming an unblocked run.
  - `fallback_plan` — degradation paths using the availability-gate wording
    ("when the checkout runtime is available").
  - `baseline_dimensions` — `sla`, `concurrency_limits`, `adoption_metrics`,
    each `{basis: baseline_run, dimension, commitments: null}`: present,
    labeled, never hand-filled.
- `validate_human_brief_payload` validates the block fail-closed with
  named-field errors.
- PRODUCT.md §4.2 and §7.2 reference the operating-model fields with the
  baseline-run framing.

## Impact

- `assets/human-brief-template.md`, `src/research_tree/delivery.py`,
  `PRODUCT.md`, and the regenerated host packages; new tests in
  `tests/test_human_brief_operating_model.py`.
- Existing Human Brief consumers are unaffected: the acceptance gate reads
  required reasoning fields by name and the delivery pair digest/manifest
  machinery is untouched, so the added document key does not break
  `acceptance.py`, `readiness.py`, or the coordinator completion manifold.
- No stored-history migration: new writes only (alpha3 zero-compat ruling).

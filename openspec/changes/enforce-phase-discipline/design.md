## Context

Issue #492: phase discipline is designed but not enforced. The tree-state
payload gate (`tree_state.py:120-147`) validates schema keys with no phase
concept, so nothing downstream can know "we are in research now". The SKILL
prose ("Autonomy envelope after strategy handoff") authorizes silent internal
successor revisions after compilation, contradicting the product rule
进入编译阶段后不可改，改就要重新对齐. The lifecycle hook classifies
interruption prompts (issue #453 signal table) but no re-entry gate is wired
to it. PR #450 established the authority fingerprint
(`strategy_projection.authority_fingerprint`) that is bound at confirmation
and re-verified at compilation; it protects display-time fields, not
post-compile drift.

## Goals / Non-Goals

**Goals:**

- One explicit run `phase` discriminator on the research-tree state payload,
  gated at every service-mediated transition.
- Post-compile strategy-material changes require user realignment (new
  confirmation + authority fingerprint) or are rejected.
- Research-phase interruptions resolve to exactly one of two protocol paths
  (reopen alignment / supplemental evidence) plus status echo; drift is
  refused with a named code.
- Correct the canonical prompt-layer prose; regenerate packages.

**Non-Goals:**

- Rewiring the alignment controller or emitting contracts (#489).
- Coordinator/CLI-side phase advancement, turn-record persistence (#497), or
  a run-phase writer inside `project_workspace.py` (workflow wiring belongs
  to later waves; the read-side seam delivered here is fail-open).
- A new `turn_contract.py` module (#501 owns that).
- Schema bump of the tree-state payload (see rejected designs).

## impact_scope

Symbols modified (GitNexus blast radius, direction upstream, index rebuilt
via `run.cjs analyze` at branch tip 4a880bd):

| Symbol | Risk | Direct upstream callers | Affected processes |
|---|---|---|---|
| `tree_state.validate_tree_state_payload` | LOW | `_normalized_state`, `CanonicalResearchTreeStateService.latest` | finalize_delivery, initialize |
| `tree_state.CanonicalResearchTreeStateService.initialize` | LOW | `CanonicalRecursiveResearchCoordinator.initialize` | initialize |
| `tree_state.CanonicalResearchTreeStateService.transition` | LOW | `ingest`, `recover`, `finalize_delivery` | finalize_delivery |
| `tree_state._normalized_state` | LOW | `initialize`, `transition` | finalize_delivery, initialize |
| `lifecycle_hook.observe` | LOW | `main` | main |
| `lifecycle_hook._observe_prompt_signal` | LOW | `observe` | main |
| `lifecycle_hook._feed_correction_signal` (generalized) | LOW | `_observe_prompt_signal` | main |

`classify_prompt_signal` semantics are unchanged (correction/interruption
records keep their meaning); the re-entry layer is additive. Detect-changes
reconciliation against this table is recorded in `evidence/` before push.

## Decisions

### Phase is optional-but-gated on the payload, defaulting at birth

Every research tree is born from a compiled, confirmed handoff, so the
service injects `phase="compiled"` when a written payload omits it and
`initialize` rejects any other birth phase. `validate_tree_state_payload`
keeps its existing required-key set (legacy ledgers and the direct
`alignment_handoff` append path stay valid) but validates the three new
optional keys — `phase`, `strategy_authority_fingerprint`, `realignment` —
whenever present, and `transition` derives the previous phase (defaulting to
`compiled` for legacy payloads) and rejects any successor outside the gated
graph:

- intake → {intake, alignment}
- alignment → {alignment, compiled}
- compiled → {compiled, research, alignment}
- research → {research, validation, alignment}
- validation → {validation, delivery}
- delivery → {delivery}

Self-loops model progress inside a phase; `research → alignment` and
`compiled → alignment` are the reopen edges of the two-option protocol;
`alignment → compiled` is the recompile edge. There is no edge into
`research` except from `compiled`, so a strategy change cannot re-enter
research without recompiling through re-aligned authority.

### Post-compile realignment gate keys on the #450 fingerprint

The payload may carry `strategy_authority_fingerprint` (64-hex, the
`authority_fingerprint` composition PR #450 binds into confirmations). A
transition whose fingerprint differs from the previous state's is a
strategy-material change; it is rejected unless (a) the edge is exactly
`alignment → compiled` and (b) the payload carries a `realignment` record
(`schema: 1`, `confirmation_digest` 64-hex, `authority_fingerprint` 64-hex
equal to the payload's fingerprint, non-empty bounded `reason`) that binds
the new fingerprint to a fresh user confirmation. Dropping the fingerprint
without a realignment edge is rejected too (fail-closed). The state layer
verifies structure and binding; the confirmation text itself stays verified
by the coordinator's confirm gate (#450), which this record is designed to
reference, not replace.

### The hook resolves re-entry locally, fail-open

`lifecycle_hook.py` ships inside packages as a standalone script (issue
#453), so it cannot import the engine's ledger. Its phase source is
explicit-argument → `RESEARCH_TREE_RUN_PHASE` → run-manifest `phase` key,
ignored when absent or invalid (the hook must never break a host session).
When the phase is `research`, `resolve_research_reentry` maps the prompt to
exactly one path — `reopen_alignment`, `supplemental_evidence`,
`status_echo` — or `refused` (`research_reentry_refused`); rule order is
reopen > supplemental > status > refused, and a bare interruption ("stop")
that picks no path is refused: there is no third ambiguous path. The
resolution is persisted on the signal record and routed to the run's events
surface (`route: "research_reentry"`), mirroring the existing
`apply_correction` feed; the correction feed is generalized, not duplicated.

### Rejected designs

- **Required `phase` key + schema bump to 3**: breaks the parallel-owned
  compile path — `recursive_search.initialize_research_state` (owned by
  #494) and the direct `alignment_handoff` batch append produce payloads
  without `phase`, and persisted ledgers must stay readable. Optional with
  birth-default keeps every existing producer and ledger valid.
- **Hook reads the run ledger directly (stdlib sqlite)**: couples the
  standalone hook to engine artifact JSON internals and invites version skew
  with packaged copies; fail-open file/env sources are stable contracts.
- **Hook writes the phase into the run manifest**: violates the hook's
  fail-open, append-only observer contract; phase advancement belongs to the
  workflow layer.
- **Enforcing the realignment gate inside `coordinator.revise_strategy`**:
  coordinator.py is outside this change's file ownership; the tree-state
  transition gate is the choke point every strategy-application must pass,
  and the coordinator can adopt it without reshaping the gate.
- **Blocking the host session on refused re-entry**: the hook's contract
  (and `main`) always answers non-blocking; refusal is a named, persisted
  verdict the workflow and agent surface, consistent with the existing
  signal architecture.

## Risks / Trade-offs

- [Phase is absent on trees written by the direct handoff append until their
  first service transition] -> `tree_phase_of` defaults to `compiled`, which
  is the true birth phase of every tree; documented in the payload schema.
- [Regex re-entry classification can misroute unusual phrasing] -> rule
  table is ordered, named, and tested; refusal is the default so an
  unclassified prompt never silently opens a third path.
- [Fingerprint gate depends on writers populating the field] -> the gate is
  fail-closed once a fingerprint exists; adoption (first appearance) is
  allowed so legacy trees are not bricked, and the SKILL prose instructs
  binding the fingerprint at compile.

## Migration Plan

No data migration. Old ledgers stay readable (optional keys); new gates
apply to service-mediated writes immediately; packages regenerate from the
canonical templates in the same change.

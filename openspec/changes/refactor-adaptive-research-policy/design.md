## Context

`ResearchRunCoordinator` owns canonical lifecycle transitions, while the legacy
recursive-search implementation still stores tree-local Slot state, delivery
manifests, and completion conclusions. Existing evidence delta is scalar and
the digest is a compact projection, so neither can explain why a new branch was
selected or prove the same input will make the same decision. This change
implements groups 6 and 16 without adding a second persistence, dispatch, or
host authority.

## Goals / Non-Goals

**Goals:**

- Produce typed, deterministic, evidence-bound proposals for the five allowed
  research methods and explicit defer/reject dispositions.
- Calculate a versioned six-component delta with a serializable baseline and
  selection trace.
- Synthesize and validate versioned, lineage-rich Insight Digest values.
- Retain a compatibility projection that reports blockers or proposals but
  cannot create closure, delivery, or completion state.
- Make focused pytest, Ruff lint, and Ruff format checks part of every TDD
  slice and final evidence receipt.

**Non-Goals:**

- Persisting or accepting proposals, dispatching work, managing leases, or
  changing coordinator lifecycle state.
- Implementing alignment prompts or handoff confirmation (#59), host events or
  adapters (#60), source capture/checkpoints (#80), or SearchPortfolio
  acquisition (#83).
- Invalidating all dependent artifacts after corrections (#73).

## Decisions

### Pure policy with typed read and proposal models

`AdaptiveResearchPolicy` will consume frozen Python value objects describing
slot deficits, verified evidence, digest signals, prior outcomes, configuration,
and a policy seed. It returns proposals, deferrals, and an audit trace. It has
no `RunLedger`, filesystem, host, or coordinator mutation dependency. Returning
values rather than appending artifacts keeps lifecycle authority centralized and
makes replay direct. A ledger-writing policy was rejected because it would
duplicate coordinator authority.

### Six-component delta is an immutable comparison

The delta module will compare a normalized baseline and current evidence state
for evidence-class coverage, provenance independence, contradiction state,
oracle state, implementation uncertainty, and Slot-closure change. Each output
includes component values and references used in the comparison. Historical or
identical state yields zero delta and a no-change signal. A scalar accumulator
was rejected because it cannot distinguish a new independent source from a
closure-affecting oracle result.

### Deterministic ranking with conservative exemptions

Scores combine registered versioned weights, deficit criticality, expected
delta, method fit, penalties, and a deterministic tie-break derived from the
policy version, canonical input digest, and seed. Optional duplicates and
dominated actions become retained deferrals. P0 counterevidence, contradictions,
and required validation bypass capacity and score-only pruning. Randomized
exploration was rejected because the same evidence state must replay exactly.

### Digest is a validated input, not an authority

Insight synthesis will emit structured classified signals and exact source/slot
references, preserve previous digest lineage, and expose policy obligations.
It neither issues closure tokens nor applies a coordinator transition. Existing
legacy four-field output will be projected only for compatibility. Letting a
digest conclude completion was rejected because completion requires coordinator
verified obligations.

### Legacy recursive search becomes a projection

The compatibility layer will translate its local frontier/report signals to
policy inputs and return proposal or blocker information. It will no longer
write `complete`, close a Slot, or treat report shape, worker count, or an empty
frontier as success. Removing the module outright was rejected because current
callers need a gradual migration surface.

## Risks / Trade-offs

- [Existing callers expect legacy tree state] -> preserve read-only-compatible
  projections and explicitly reject attempted closure rather than silently
  changing the return shape.
- [Synthetic test fixtures lack complete lineage] -> define small typed fixture
  builders and reject generic worker-only inputs at the public policy boundary.
- [Score changes can alter optional choices] -> bind policy version,
  configuration, input digest, and seed in every trace; calibration creates a
  new version instead of rewriting history.
- [Formatter changes could create noisy diffs] -> run format checks in each
  slice and format only touched files.

## Migration Plan

1. Add failing policy, delta, digest, replay, and projection tests.
2. Implement pure value models and deterministic policy/delta behavior.
3. Add digest validation/synthesis and migrate only compatibility callers.
4. Remove direct legacy completion/delivery writes, replacing them with bounded
   blocker/proposal results.
5. Record group 6 and 16 verification evidence after focused and full checks.

Rollback disables policy selection and leaves existing evidence/digest records
readable; it must not restore a legacy path that writes Slot or run completion.

## Open Questions

- #83 will own persistent SearchPortfolio methods. This change accepts a
  read-only descriptor and will not resolve providers or acquire sources.
- #73 will own downstream invalidation. This change reports affected lineage to
  the coordinator but will not stale arbitrary artifacts itself.

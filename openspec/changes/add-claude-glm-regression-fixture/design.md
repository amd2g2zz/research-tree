## Context

The Alpha2 evaluation contract requires controlled comparisons for causal
claims, while Issue #72 lacks an authoritative historical transcript and a
configured GLM5.2 runtime. A reproducible fixture can still protect the
observed behavioral boundaries if it labels its inputs and result correctly.

## Goals / Non-Goals

**Goals:**

- Provide a strict public synthetic case with no provider session or hidden
  oracle body.
- Check state-transition invariants without adding a second runtime authority.
- Keep the runnable control deterministic and report the missing external
  runtime as unavailable rather than passing.
- Keep raw command output under `.research-tree/evaluation-runs/issue-72/`.

**Non-Goals:**

- Reproducing a historical Claude Code conversation.
- Inferring that GLM5.2, Claude Code, or a host configuration caused behavior.
- Launching a provider, comparing pricing or latency, or changing coordinator
  lifecycle behavior.

## Decisions

1. **Synthetic case, not reconstructed transcript.** The public JSON carries
   only labelled synthetic turns, an opaque oracle identifier, and explicit
   limitations. It has no exact historical turns, provider output, or expected
   patch.
2. **Deterministic event controls.** The runner requires activation before a
   quoted reference, exactly one bounded open question, transactional
   correction invalidation with a successor strategy, one stable task identity,
   recursive research continuation to decision-specific closure, and two
   evidence-bound deliveries. It does not score headings, bytes, URLs, or
   worker count.
3. **Causal attribution remains unresolved.** A completed comparison must hold
   all registered inputs fixed while varying only runtime, but this fixture
   itself continues to emit `unresolved`. An unavailable runtime requires a
   blocker id and cannot make the result pass.
4. **Evaluation-owned raw-output boundary.** The receipt helper retains its
   repository escape check while allowing the two existing ignored roots:
   verification runs and evaluation runs. Group 24 uses the latter so raw test
   and fixture output stays co-located with evaluation evidence.

## Risks / Trade-offs

- **Synthetic controls may be mistaken for live evidence.** The case, result,
  runner status, and OpenSpec all state that it is non-historical and cannot
  establish live parity or causation.
- **Public fixtures can leak evaluator material.** The runner rejects forbidden
  keys and the existing evaluation asset checker enforces the governed boundary.
- **Unavailable external runtime can hide a regression.** The result remains
  non-passing and names the blocker, preserving the work needed for a future
  controlled run.

## Migration Plan

1. Add red tests and record their local ignored output.
2. Add the public schema, case, deterministic harness, and constrained receipt
   boundary.
3. Commit the source slice, run the registered command, and record the
   source-bound unavailable receipt/result before truthfully completing group 24.

## Open Questions

A future operator-controlled execution may supply a completed comparison only
when both runtimes and all fixed input digests are available. That external
evidence remains outside this delivery.

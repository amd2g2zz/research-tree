## Context

The tagged Alpha1 release is a historical baseline, not a current release
candidate. Its regressions must be represented in tracked evaluation source so
later Alpha2 work can prove improvement without encoding answers in a manifest
that an implementing worker reads. The existing generic evaluation corpus is
for independent software-change evaluation and cannot express research-tree's
host, completion, recovery, and evidence failure modes.

## Goals / Non-Goals

**Goals:**

- Pin a stable Alpha1 revision and package identities.
- Define public replay metadata for representative failures across all hosts.
- Keep unsafe expected outcomes evaluator-owned.
- Make all result classifications deterministic and evidence-bearing.
- Make malformed, stale, duplicate, and answer-leaking fixtures fail fast.

**Non-Goals:**

- Run external providers or reproduce every case during unit tests.
- Claim a current Alpha2 implementation fixes an Alpha1 issue.
- Deliver cross-host release gates, raw transcripts, or the paired benchmark.
- Add a new runtime completion authority.

## Decisions

### Public manifest plus evaluator-owned oracle registry

`evaluation/cases/alpha1-adversarial-v1.json` is tracked and readable by a
worker. It records the pinned baseline, host, replay command, case category,
and opaque oracle identifier. It MUST NOT include expected unsafe outcomes,
hidden prompt material, or evaluator implementation details.

`src/research_tree/alpha1_adversarial.py` owns the oracle registry. It maps
the opaque identifier to a concise risk statement and is the only component
that classifies an observation. This is a code boundary, not a secrecy claim:
release evaluators may replace it with an external hidden oracle, while normal
repository tests verify that public fixture material cannot contain an answer.

Alternative: one self-contained JSON file. Rejected because it exposes the
target behavior to the component being evaluated.

### Baseline identity is immutable and validated

The manifest MUST pin tag `0.0.1-a1`, its resolved 40-character commit
`8ab91ea4eb55c98441b5ee6001b80922a56ecdd1`, and separately named Codex,
Claude Code, and Hermes package locations. A validator rejects tag-only,
shortened, malformed, or mismatched identity fields.

Alternative: current branch as baseline. Rejected because it makes later
results non-reproducible.

### Conservative three-way classification

For each case, `observed_unsafe=True` yields `vulnerability_reproduced`.
`observed_unsafe=False` with no corroborating candidate evidence yields
`inconclusive`, never a fix claim. A `fix_confirmed` result requires at least
one nonempty evidence reference. Result receipts include schema version,
baseline identity, case/oracle identifier, status, command receipt, and
evidence references.

Alternative: binary pass/fail. Rejected because absence of a reproduction is
not evidence of a fix.

### One focused corpus with representative categories

The first corpus contains nine cases: forged validation, missing evidence,
filler report acceptance, empty frontier completion, ignored contradiction,
repeated reconnaissance, adapter-only completion, provider failure without a
successor, and crash recovery obligation loss. Initial inspection shows the
Alpha1 checkout does not retain direct replay commands for these cases, so all
are explicitly `unavailable` with reasons. The fixture does not invent a
runnable command; later quality work must add a verified reproduction runner.

## Risks / Trade-offs

- [An Alpha1 test path differs from the historical checkout] -> retain the
  command as historical metadata and classify execution availability separately.
- [Oracle registry is visible in the repository] -> treat it as a test-double
  boundary; release evaluation can supply an independent oracle implementation.
- [Case count implies completeness] -> label the corpus representative and
  require later #64/#84 work to expand and score it.
- [Stale baseline package paths] -> validate required host keys, but defer
  package installation verification to host-specific evaluation issues.

## Migration Plan

1. Add the manifest, evaluator module, and tests without modifying current runtime.
2. Validate the baseline tag resolves locally and commit the source together.
3. Register the acceptance command as task group 1 evidence.
4. Later quality work consumes this manifest rather than moving or rewriting
   it; a new corpus version is additive.

Rollback removes this corpus revision and its evaluator only. It does not
delete the immutable Alpha1 tag or historical run evidence.

## Open Questions

None for the local baseline contract. Independent hidden-oracle infrastructure
is intentionally deferred to the release evaluation issue.

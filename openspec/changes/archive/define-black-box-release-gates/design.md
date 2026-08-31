## Context

Evaluation assets now have a governed namespace, stable public case identifiers, safe opaque oracle references, and deterministic validators. The runtime also persists authoritative evidence, source captures, checkpoints, semantic deliveries, recovery state, and host events. The remaining release gap is a deterministic evaluator-owned manifest that composes those artifacts without exposing hidden oracle bodies or accepting proxy metrics as completion.

## Goals / Non-Goals

**Goals:**

- Keep worker-visible public inputs physically and structurally separate from evaluator-owned oracle execution.
- Evaluate integrity gates before semantic quality diagnostics and make every failed gate non-waivable.
- Represent Codex, Claude Code, and Hermes as equivalent logical host observations while recording unavailable capabilities honestly.
- Persist enough case, command, environment, artifact, evaluator, oracle, review, and limitation metadata for offline verification.
- Permit independent implementation and blinded expert evidence without making either a sole authority.

**Non-Goals:**

- Launching live provider or host processes inside the unit-test suite.
- Publishing hidden oracle bodies, expected patches, raw prompts, credentials, or private reasoning.
- Replacing runtime completion authority or modifying #82 native workflow adapters.
- Completing the later paired benchmark, migration, or provider-specific regression issues.

## Decisions

1. **Use one typed release manifest and pure evaluator.** A `ReleaseManifest` contains versioned public case results and evidence references; `evaluate_release()` returns a deterministic `ReleaseDecision`. This makes the release oracle replayable without introducing another writable runtime authority. The alternative, deriving readiness from CI job names or result-directory presence, was rejected because those are self-reported and not source-bound.

2. **Separate integrity gates from quality diagnostics.** Zero false completion, P0 resolution, evidence/closure resolution, hidden-oracle isolation, recovery, semantic delivery consistency, and canonical host parity are hard gates. Quality metrics and expert review are retained diagnostics with declared thresholds, but cannot offset an integrity failure. A single weighted score was rejected because it permits a severe integrity failure to be averaged away.

3. **Treat unavailable host execution as unavailable.** Each required host has an execution disposition of `passed`, `failed`, or `unavailable` with a limitation. A release candidate cannot claim parity when a required host is unavailable, although the evidence remains useful for diagnostics. Fabricating fallback parity was rejected because host capability absence is a release limitation, not a pass.

4. **Keep hidden material behind opaque identifiers.** Public manifests contain stable oracle IDs and result digests only. The evaluator ingests signed/hashed verdict records supplied outside worker-visible case material and rejects forbidden hidden keys or leaked expected content. Co-locating expected answers with public cases was rejected because it contaminates the black-box boundary.

5. **Persist release evidence under governed evaluation paths.** Schemas, public case definitions, harness metadata, retained redacted results, and review records live in their registered lifecycle classes. Disposable run output and raw transcripts remain outside tracked source paths.

## Risks / Trade-offs

- **[Synthetic fixtures can overstate live parity]** → Mark live host execution separately and require unavailable dispositions until an external runner produces equivalent canonical artifacts.
- **[Semantic thresholds can be gamed]** → Preserve per-metric observations and limitations, require independent implementation plus blinded review, and never allow quality scores to waive integrity gates.
- **[Oracle leakage through result metadata]** → Reject hidden fields and secret-like keys, store only opaque IDs/digests, and run the evaluation asset validator.
- **[Large retained evidence burdens review]** → Keep the PR to schemas, public fixtures, evaluator code, and compact redacted results; raw runs remain disposable/untracked.

## Migration Plan

1. Add the issue-local specification and focused failing tests.
2. Add typed manifest/decision evaluation and governed public schemas/cases.
3. Register deterministic acceptance commands and source-bound group-12 evidence.
4. Roll back by disabling candidate gating while retaining immutable evaluation evidence and manifests read-only.

## Open Questions

- Live Claude Code and Hermes provider evidence remains an external capability; absent execution is recorded as unavailable and cannot satisfy the final release candidate until later host-specific fixtures provide evidence.

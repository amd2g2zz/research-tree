# Issue #268: Alpha2 Comprehensive Evaluation Design

Status: design complete for implementation handoff; benchmark execution is not claimed.

This document freezes the smallest evaluation program that can support a useful
Alpha2 decision without confusing a contract fixture, a pilot, or a host smoke
with evidence of research quality.

## 1. Decision And Scope

The primary decision is whether Alpha2 improves evidence-backed research
behavior over the pinned Alpha1 implementation. The native host baseline is a
secondary reference point, not a prompt-only ablation.

The evaluation owns the design contract and the redacted research artifacts.
Issue #84 owns benchmark implementation, sealed execution, and result evidence.
Issue #244 owns real-host conformance prerequisites. Issue #67 consumes accepted
benchmark evidence for release closure.

The evaluation does not change runtime semantics, tune the runtime against the
hidden holdout, or call a synthetic-user score human satisfaction evidence.

## 2. Frozen Arms

Each host has the same three arms:

| Arm | Definition | Required isolation |
|---|---|---|
| B | Native host with no Research Tree package, skill, hook, or runtime state | A fresh host home/config proves no RT activation |
| A1 | Pinned Alpha1 package and runtime revision | Package, hook, model, provider, and settings are digested |
| A2 | Pinned Alpha2 candidate package and runtime revision | Same binding rules as A1 |

The primary contrast is `A2 - A1`. Secondary contrasts are `A1 - B` and
`A2 - B`. The baseline is not a simplified copy of the Alpha2 prompt. B must
run the same user input against the native Claude Code, Hermes, and Codex host
surfaces when those cells are required.

The target host matrix is nine cells: `B/A1/A2` for `codex`, `claude-code`,
and `hermes`. A missing host or arm is `unavailable`; it is never substituted
with another host, model, or wrapper result.

Every cell records:

- source revision, arm revision, host package digest, runtime and hook digest;
- model, provider, endpoint, sampling settings, tool policy, and rootfs digest;
- command digest, environment digest, source-capture policy, and task seed;
- loaded-skill observation for B and activation receipt for A1/A2; and
- raw event, source, output, and ledger artifact references.

## 3. Data Design

The independent unit is a task cluster, not a model turn, token count, or
report paragraph. Each cluster is a fixed input plus its source policy,
interaction script, hidden checks, and delivery rubric.

The minimum formal corpus contains 24 clusters, six per family:

1. **Research and source conflict**: multi-hop retrieval, source quality,
   independent corroboration, and incompatible claims.
2. **Alignment and correction**: ambiguous intent, one human-owned decision,
   correction after an initial plan, and a bounded replan.
3. **Recovery and contradiction**: process interruption, stale evidence,
   contradictory findings, resume, retraction, and closure reopening.
4. **Implementation handoff**: repository or technical investigation whose
   report is given to an independent implementer with no hidden answer.

Long-horizon interaction is embedded in families 2 and 3. Fault injection is a
replayable perturbation of those clusters, not a second expensive dataset.

The corpus has three layers:

- **Visible deterministic layer**: frozen source captures and public checks for
  harness development and debugging.
- **Evaluator-owned hidden layer**: five clusters, at least one from every
  family, held outside the repository. Only a manifest digest and opaque oracle
  identifiers are tracked.
- **Live variation layer**: a small predeclared sample rerun against live web
  sources. It retains captures and timestamps and is reported as environmental
  variation, never silently merged with deterministic replay.

The existing `alpha1-adversarial-v1` and `host-conformance-v1` assets remain
contract and integrity fixtures. They do not count as the 24 research-quality
clusters.

## 4. Execution And Cost Control

The default formal run is:

- 24 clusters x 3 arms x 3 hosts = 216 base executions;
- eight long-horizon or recovery clusters repeated once = 72 additional
  executions;
- deterministic fault scripts with no model call;
- 12 stratified output bundles for blinded review; and
- eight reports for independent implementation testing.

This is an upper bound, not a command to spend the budget blindly. Execution is
sequential and predeclared:

1. Run an eight-cluster pilot across all nine cells (72 executions). The pilot
   checks host availability, paired variance, integrity, and cost. It cannot
   declare an Alpha2 quality win.
2. Continue with the remaining 16 clusters only if every required cell is
   executable and no hard gate is failing.
3. Add repeats only to the predeclared reliability panel. If uncertainty is
   concentrated in one family, expand that family rather than rerunning all
   cells.

The pilot and formal run use the same sealed manifest shape. A pilot result is
labelled `pilot` and cannot be copied into a release result.

All arms share the task input, source snapshot, seed, repetition identity, and
declared budget for a pairing key. Provider and host costs are recorded as
diagnostics; failures remain in the denominator and are not silently excluded.

## 5. Metrics And Oracles

### Hard integrity gates

These gates are pass/fail and cannot be offset by quality scores:

- zero false completion under normal and injected-fault runs;
- every consequential claim has a current, resolved evidence and closure path;
- P0 findings are resolved or explicitly unavailable;
- resume preserves accepted work and creates a fresh attempt where required;
- replay reconstructs the same canonical outcome or records divergence;
- no synthetic identity, self-reported capability, or unbound artifact is
  accepted; and
- every required host/arm cell has a valid, source-bound result.

### Quality and experience diagnostics

The formal primary endpoint is the task-cluster rate of an evidence-backed,
implementation-ready result. Secondary metrics are intent fidelity, correction
assimilation, source support precision/coverage, contradiction handling,
rediscovery burden, recovery usefulness, report usefulness, and independent
implementation success.

Each metric definition must specify polarity, numerator and denominator,
scoring rubric, missing-data rule, evidence reference, and confidence method.
Cost, latency, token use, and tool actions are reported separately and cannot
replace semantic outcomes.

Synthetic-user trajectories can measure state transitions and policy adherence;
they cannot establish human satisfaction. Blinded human review retains rater
identity separation and disagreement. Independent implementation is scored from
the report and public repository state only.

## 6. Statistical Analysis

The unit of inference is the paired task cluster within a host. Do not pool
Claude Code, Hermes, and Codex into one primary estimate.

- Compute task-level `A2 - A1` differences per host and family.
- Use paired bootstrap confidence intervals over task clusters.
- Use a seeded sign-flip permutation test for the primary contrast when a
  p-value is required; apply Holm correction only to predeclared secondary
  contrasts.
- Report effect size, 95% interval, sample count, failures, and unavailable
  cells together. Never report a mean without its pairing and denominator.
- Treat 24 clusters per host as a planning target for a medium-to-large paired
  effect (approximately `d=0.6`); detecting `d=0.5` requires about 32 clusters
  per host. The pilot estimates variance but cannot be used as a success test.

An incomplete pairing is retained as a failure or unavailable observation. It
is not imputed, replaced by another host, or removed because it is expensive.

## 7. Artifact And Privacy Contract

Evaluator-owned manifests, holdouts, prompts, oracle bodies, credentials, and
raw transcripts remain outside tracked paths under
`.research-tree/evaluation-runs/<run-id>/`. Tracked results contain only
redacted summaries, digests, opaque oracle IDs, limitations, and reachable
artifact references.

Every formal result binds the exact source revision and manifest digest. A
changed arm, package, host image, corpus, reviewer assignment, or command
creates a new result identity. Historical or pilot output cannot be relabelled
as the formal result.

## 8. Implementation Handoff To #84

1. Add the native no-RT baseline cell and prove its clean host home/config.
2. Extend the paired manifest from the current two-host pilot to the required
   nine-cell matrix, or record an explicit conditional disposition before any
   run.
3. Add the 24-cluster corpus contract, five hidden holdout digests, and the
   task-to-family/rubric map without embedding hidden answers.
4. Reuse the existing evaluator-owned journal, source broker, synthetic-user
   boundary, host-conformance fault cases, and paired statistics implementation.
5. Run the eight-cluster pilot and retain a separate pilot result.
6. Run the formal matrix only after all hard gates and provider access are
   frozen; then publish the redacted result and independent review evidence.

## 9. Closure Rule

Issue #268 is design-complete when this document, the Technical Research
Package, and the Human Research Report are tracked and reviewable. It is not
benchmark-complete. Issue #84 may close only after a formal result is bound to
the final manifest, all required cells have an explicit disposition, hard gates
pass, paired analysis is reproducible, and human/implementation evidence is
retained. Issue #67 may consume that result only after the merge and reachability
checks succeed.

# Technical Research Package: issue-268-evaluation

This active evaluation package is indexed from [evaluation documentation](../README.md).

## Round, Context, And Current Scope

- Round: `issue-268-evaluation`, revision `1`
- Repository baseline: `origin/dev` at `93c2d601c7ac0e07f504c89a0d112e4cef71ff64`
- Trigger: Issue #268 asks for a governed Alpha2 evaluation design before #84
  executes the paired benchmark.
- Current scope: freeze arms, host matrix, task clusters, statistics, hard
  gates, artifact retention, and the implementation handoff.
- Non-goals: runtime changes, benchmark execution, model tuning, or release
  promotion.

## Intent Rewrite

Define the smallest reproducible evaluation contract that can distinguish
native host behavior from Alpha1 and Alpha2 while measuring evidence integrity,
long-horizon interaction, recovery, human usefulness, and implementation
readiness. The contract must make cost and unavailable capabilities visible
without turning a pilot or synthetic result into a release claim.

## Feasibility

- Disposition: `conditional`
- Confidence: `high` for design; `low` for execution readiness
- Conditions: evaluator-owned holdouts, exact arm and host digests, provider
  access, native no-RT baselines, and independent reviewers must exist before
  the formal run.

The design is operationally plausible because the repository already contains
host-conformance gates, a release evaluator, a paired-statistics module on the
#84 branch, and an evaluator-owned journal boundary. It is not executable as a
formal benchmark from the current checkout because the sealed corpus and final
nine-cell receipts are absent.

## Current Technical Baseline

| Observation | Evidence | Consequence |
|---|---|---|
| Release replay is deterministic and fails required Hermes parity | `evaluation/harness/run_release_gates.py` on `origin/dev`; result status `fail`, gate `required_host_parity: hermes` | Do not treat retained release JSON as benchmark evidence |
| Public Alpha1 asset validation covers nine cases | `scripts/check_evaluation_assets.py --public-alpha1` | Shape/provenance validation is not quality evaluation |
| Host conformance has fault/replay negative oracles | `evaluation/cases/host-conformance-v1.json` and related harness/tests | Reuse for integrity, not as research-quality data |
| The #84 branch has sealed paired protocol and statistics | `test/issue-84-paired-benchmark` at `8a3c36d` | Reuse the boundary; add native baseline and nine-cell contract |
| #268 design path is not tracked at baseline | Issue comment names the path, but no tracked file/commit is reachable | This package supplies the missing design artifact |

## Decision Slots

| Slot | Decision | Status | Closure oracle |
|---|---|---|---|
| D1 | What is the baseline? | selected | Clean native host run proves no RT package, hook, or state was loaded |
| D2 | What data size supports a useful claim? | selected | 24 paired task clusters/host, with pilot and effect-size limitation recorded |
| D3 | What can block release? | selected | Hard integrity gates fail independently of quality diagnostics |
| D4 | What counts as human evidence? | selected | Blind review and independent implementation are separate from synthetic-user traces |
| D5 | How is cost bounded? | selected | Eight-cluster pilot, selective repeats, frozen replay, and family-level expansion |

## Research Findings

1. A simpler prompt is not a valid native baseline for a skill/runtime system;
   the baseline must run the host without Research Tree installation or hooks.
2. Existing contract fixtures prove lifecycle semantics but cannot estimate
   research quality. They must not be counted as benchmark task clusters.
3. Long-horizon interaction, recovery, and fault injection can share task
   clusters. Separate large datasets would increase cost without adding an
   independent unit of inference.
4. Repeats estimate execution reliability; independent task clusters provide
   statistical power. Repeating one task many times cannot replace diverse
   task clusters.
5. Host-specific analysis is required. Pooling host outputs would hide a
   host-specific failure behind an average.
6. A formal result must distinguish `pilot`, `executed`, `failed`, and
   `unavailable`; a report or sealed manifest alone is not execution evidence.

## Recommended Design

The detailed contract is in
`docs/evaluation/research/issue-268-comprehensive-evaluation-design.md`. The essential
interfaces are:

- a sealed manifest binding arm, host, model, runtime, corpus, seed, command,
  and reviewer assignment digests;
- a task-cluster record with family, public/hidden status, source policy,
  interaction script, oracle ID, and rubric digest;
- append-only episode journal events for activation, turns, tool/source
  actions, faults, recovery, delivery, and final disposition;
- a redacted result containing per-cell status, hard-gate outcomes, task-level
  metrics, paired differences, intervals, failures, and limitations; and
- separate review and implementation evidence referenced by digest.

## Implementation Plan

| Order | Work item | Owner | Validation |
|---:|---|---|---|
| 1 | Register the native no-RT baseline and clean-home proof | #84 | One baseline smoke per required host; missing host is unavailable |
| 2 | Extend the manifest to nine host/arm cells | #84 | Exact digest and anti-confounding validator |
| 3 | Seal 24 task clusters and five hidden holdout digests | evaluator | Holdout not readable by runner; public replay deterministic |
| 4 | Run eight-cluster pilot | #84 | Pilot result separate; no quality promotion |
| 5 | Run formal paired matrix and selective repeats | #84 | Host-stratified paired analysis, raw journal, redacted result |
| 6 | Review and independent implementation | evaluator | Blind assignments, retained disagreements, implementation receipts |
| 7 | Consume the accepted result | #67 | Reachable merge, hard gates, package/docs/governance checks |

Rollback is to retain the immutable design and pilot/unavailable evidence while
reverting only the benchmark execution branch. No runtime behavior is changed
by this design.

## Evidence And Readiness

| Gate | Result | Evidence |
|---|---|---|
| Scope and authority | pass | #268 owns design; #84 owns execution; #67 owns release consumption |
| Feasibility | conditional | Holdout, provider, host, and reviewer authorities are still external |
| Repository fit | pass | Existing evaluation, conformance, journal, and statistics boundaries are reusable |
| Statistical design | pass with limitation | 24 clusters target medium-to-large effects; smaller effects need expansion |
| Execution readiness | deferred | No formal nine-cell result or evaluator-owned holdout is present |
| Artifact integrity | pass for design | This package is a proposed/design artifact, not executed benchmark evidence |

## Source Ledger

| ID | Source | Class | Use | Limitation |
|---|---|---|---|---|
| S1 | Issue #268 body and comment | repository/issue | Scope, deliverables, 9-cell target, execution boundary | Comment did not include a commit for the named design file |
| S2 | Issue #84 body/comments | repository/issue | Execution ownership, paired protocol, unavailable rules | #84 remains open and formal result is absent |
| S3 | `evaluation/harness/run_release_gates.py` | repository | Retained replay behavior | Does not execute hosts |
| S4 | `evaluation/cases/host-conformance-v1.json` | repository | Fault, replay, and negative-oracle cases | Not a research-quality corpus |
| S5 | #84 branch `8a3c36d` paired harness | repository | Sealed manifest, journal, Docker boundary, statistics | Unmerged two-host implementation; one Windows file-mode test is platform-sensitive |
| S6 | [tau-bench](https://github.com/sierra-research/tau-bench) | external primary project | Dynamic user/tool trajectory separation | Domain-specific and not a human-satisfaction oracle |
| S7 | [OSWorld](https://github.com/xlang-ai/OSWorld) | external primary project | Real-environment execution and trace-oriented verification | Computer-use domain, not research-tree semantics |

## Completion Boundary

This package is `source-inspected` and `built` as a design document. It is not
`executed` benchmark evidence. The next decisive artifact is the evaluator-owned
sealed manifest plus the eight-cluster pilot result.

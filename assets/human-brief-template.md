# Human Brief: {{round_id}}

This brief is the operating model for the run, not only a report: the seven
operating-model fields below tell the requester who acts, within what limits,
what blocks completion, what the outcome layers say, how adoption is measured,
and what degrades when a capability is unavailable. Fields sourced from runtime
artifacts carry real run output; baseline-run fields carry measured baselines,
not commitments.

## Roles

| Role | Responsibility | Handoff surface |
|---|---|---|
| {{research owner}} | {{Owns the research outcome: keeps the Living Brief honest, closes Decision Slots with evidence, registers per-oracle goal_satisfaction verdicts from real run artifacts.}} | {{Hands the confirmed projection, Finding Packs, and the Technical Research Package to the implementation agent with origin labels; hands unresolved blockers to the human requester at the decision gate.}} |
| {{platform integrator}} | {{Installs and operates host packages and runtime hooks; keeps agent, worker, and tool content distinguishable through the closed origin vocabulary (user | agent | worker | tool | repository | generated).}} | {{Receives host-install and capability findings from the research owner; returns availability facts (install status, runtime availability, fallback state) to this view.}} |
| {{governance auditor}} | {{Audits evidence custody, authority fingerprints, and completion claims; independent review is a distinct execution, not a relabeled self-check.}} | {{Receives the delivery pair digests, the blocker list, and quarantine records; returns acceptance, waiver, or rejection with reasons.}} |

## SLA

Basis: baseline run — measured values from the first operating-model run,
not commitments.

| Stage | Measured baseline | Commitment |
|---|---|---|
| {{alignment confirmation time limit}} | {{measured}} | {{none yet}} |
| {{dispatch response}} | {{measured}} | {{none yet}} |
| {{delivery window}} | {{measured}} | {{none yet}} |

## Concurrency limits

Basis: baseline run — measured ceilings and over-limit behavior, not
commitments.

- Concurrent slots observed: {{measured ceiling and over-limit behavior}}
- Concurrent runs observed: {{measured}}

## Blockers

The current blocker list comes from real run output, not recollection: the
resolve entries of `why_not_complete` (for example `resolve:goal_satisfaction:{{oracle_id}}`),
each with an owner role and the action that clears it. When the checkout
runtime is available, take the list from the runtime's why-not-complete
output; otherwise persist the equivalent blocker table yourself and label its
origin.

| Blocker | Resolution condition | Owner |
|---|---|---|
| {{obligation}} | {{resolve: entry}} | {{research owner / platform integrator / governance auditor / human requester}} |

## Outcome layers

Outcome is shown in layers, never flattened into one claim:

1. Confirmed projection (top layer): the projection the run lifecycle
   authoritatively confirmed (the latest confirmed projection), with its
   display digest and authority fingerprint.
2. Per-oracle goal_satisfaction verdicts: one registration per success oracle
   (satisfied | partial | unmet | waived, with the waiver reason when waived).
3. Slot contribution summary: per-slot contribution verdicts from the run's
   goal-contribution assessments, latest per finding pack.

| Layer | Value | Source |
|---|---|---|
| {{Confirmed projection}} | {{id@revision, display digest, authority fingerprint}} | {{latest confirmed projection}} |
| {{Oracle verdict}} | {{oracle_id: satisfied/partial/unmet/waived}} | {{goal_satisfaction registration}} |
| {{Slot contribution}} | {{slot: pack — verdict (reason)}} | {{goal-contribution assessment}} |

## Adoption metrics

Basis: baseline run — the first operating-model run's values are the baseline,
not commitments.

| Metric | Measured baseline | Trend |
|---|---|---|
| {{Run count}} | {{measured}} | {{...}} |
| {{Completion rate}} | {{measured}} | {{...}} |
| {{Waiver rate}} | {{measured}} | {{...}} |
| {{Noise trend}} | {{measured}} | {{...}} |

## Fallback plan

Runtime verbs supply blocker and completion diagnostics when the checkout runtime is available;
otherwise persist the equivalent tables from the persisted artifacts and label their origin.
Record an unavailable host
capability (Codex, Claude Code, Hermes) as a blocker with its resolution
action instead of inferring success. Downgrade unreachable external sources to
repository or supplied-material evidence with the limitation recorded.

- {{capability}}: {{understandable degraded path}}
- {{capability}}: {{understandable degraded path}}

## What We Now Understand

{{The current joint understanding of the desired outcome and why it is stronger
than the original wording. Separate explicit user intent from agent inference.}}

- Living Brief revision/state: {{...}}
- Current intent rewrite: {{...}}
- Reasonable scope expansion and guardrails: {{...}}
- Authority boundary: {{...}}

## How Understanding Changed

| Change | Trigger/evidence | Effect on the direction |
|---|---|---|
| {{User corrected the agent}} | {{anchor}} | {{...}} |
| {{Agent corrected itself}} | {{anchor/evidence}} | {{...}} |
| {{Evidence changed a shared assumption}} | {{anchor}} | {{...}} |

## Alignment Trace

{{Summarize the meaningful alignment turns, not the full conversation. Show the
one gap explored per turn and how the human and agent models changed.}}

| Turn | Gap explored | Evidence/teaching | What the requester clarified | Resulting change |
|---|---|---|---|---|
| {{AT-1}} | {{...}} | {{...}} | {{sanitized summary}} | {{...}} |

## Recommended Technical Direction

{{The capability, architecture direction, and first useful working loop.}}

## Feasibility Verdict

- Disposition: {{plausible|conditional|infeasible|indeterminate}}
- Why: {{plain-language bounds, baselines, prerequisites, and confidence}}
- Conditions or conflicting constraints: {{...}}
- Nearest feasible alternatives: {{when applicable}}
- Next feasibility test: {{when indeterminate}}

{{If infeasible, state that directly and omit an implementation direction. Do
not turn a negative finding into an aspirational roadmap or silently select one
of the feasible alternatives.}}

## Important Choices

| Choice | Why it matters | Main trade-off | Reversal condition |
|---|---|---|---|
| {{...}} | {{...}} | {{...}} | {{...}} |

## Evidence Confidence

{{What was inspected, cross-checked, or tested; which claims are still
single-source, inferred, contradictory, or environment-dependent.}}

## What Actually Exists

| Output | Evidence level | Location/result | What is not yet proven |
|---|---|---|---|
| {{...}} | {{proposed|source-inspected|built|executed|independently-reviewed}} | {{...}} | {{...}} |

## Near-Term Result

{{The next visible milestone and its validation oracle.}}

## Open Disagreements and Uncertainty

{{The few issues that could still change the outcome, scope, or direction, with
their next validation or human decision.}}

## Implementation Readiness

{{Which high-impact decisions are closed, conditional, deferred, or blocked.}}

## Technical Package

{{Path/reference to the agent-facing package. Mention OpenSpec only if requested.}}

## Human Decision Gate

- Status: {{pending|accepted|needs-revision|blocked}}
- Requester satisfaction anchor: {{explicit acceptance or unresolved objection}}
- Required revision/evidence batch: {{...}}

{{Use plain language. Never describe a report, schema, pseudocode, or proposed
implementation as a working system.}}

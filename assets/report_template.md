# {{intent_title}}

- Snapshot: `{{snapshot_id}}`
- As of: `{{reference_time}}`
- Evidence window: `{{evidence_window}}`
- Decision status: `{{proposal | partial result | completed finding}}`

Use the standard profile for a bounded research answer. When the frozen
deliverables include a material-design or experiment plan, use the
**experiment-plan profile** below. It is a decision document, not a compressed
copy of its chapters.

## Decision-Aware Overlay

Use this overlay whenever the frozen editor packet contains a
`decision_synthesis`. It is mandatory in addition to the selected profile.
The synthesis is the source of truth: do not convert a conditional, deferred,
or preflight-only recommendation into an approval.

<!-- research-tree:decision-synthesis {{decision_synthesis_sha256}} -->

## Decision Assessment

### {{decision_question}}

<!-- research-tree:decision-question {{decision_question_id}} -->

{{State the bounded conclusion, then make the chain explicit: frozen evidence
and cited source -> inference -> action now. Distinguish evidence from a
proposal or assumption.}}

## What Would Change The Decision

- {{Condition, missing measurement, recursive child result, or user answer
  that could change the conclusion.}}

## Parameter Provenance

| Parameter | Value | Basis | Evidence or rationale | Decision effect |
|---|---|---|---|---|
| {{parameter}} | {{value}} | {{user_constraint | direct_evidence | transfer_method | assumption | need_user_input}} | {{source or reason}} | {{how this affects the recommendation}} |

<!-- research-tree:parameter {{parameter_id}} -->

Do not introduce an exact numeric threshold, sample size, cost, schedule, or
operating value unless it appears here with its frozen provenance. A design
choice or assumption must be visibly labeled as such.

## Standard Profile

## Answer

{{A direct answer bounded by the frozen evidence, time window, and audience.}}

## Material Findings

### {{finding_title}}

{{Claim or inference.}} [E1]

{{State whether this is a source fact, an inference, a user-material fact, or
a proposed choice.}}

<!-- research-tree:evidence {{chunk_id}} -->

## Contradictions and Changes Over Time

- {{Competing claim or changed condition, with evidence labels for each side.}}

## Limits and Open Gaps

- {{Insufficient evidence, access limit, deferred work, or required user input.}}

## Sources and Traceability

| Label | Source and date | What it supports | Evidence limits | Frozen location |
|---|---|---|---|---|
| [E1] | {{title, publisher/provider, published or retrieved date}} | {{bounded use}} | {{quality, directness, completeness, or transfer limit}} | `{{source_path}}`, {{locator}} |

Keep the machine-readable frozen chunk identifier in an HTML comment adjacent
to the supported claim or ledger row. Do not render `[citation: c_...]` in
reader-facing prose.

## Experiment-Plan Profile

Use this profile when the intent requires an experiment, operational design, or
other material-backed plan. Retain the headings even when a section concludes
that the plan cannot proceed.

## Decision Summary

{{State the decision requested, the recommended action now, and whether this
is a proposed protocol rather than an observed result.}}

## Scope and Inputs

{{Separate supplied-material facts, frozen external evidence, assumptions, and
proposed choices. State non-goals and hard constraints.}}

## Evidence Judgment

| Label | Source and date | Design use | Directness and completeness limit |
|---|---|---|---|
| [E1] | {{readable source}} | {{bounded design implication}} | {{what it cannot establish}} |

<!-- research-tree:evidence {{chunk_id}} -->

## Experiment Design

| Element | Protocol |
|---|---|
| Decision question | {{question}} |
| Treatment | {{intervention}} |
| Control | {{baseline}} |
| Unit and pairing | {{unit, blocking, randomization}} |
| Invariants | {{versions, inputs, environment, exclusions}} |

## Metrics and Adjudication

| Measure | Numerator | Denominator | Decision time | Missing or invalid run rule | Owner and review |
|---|---|---|---|---|---|
| {{primary outcome}} | {{...}} | {{...}} | {{...}} | {{...}} | {{...}} |

Include an explicit failure taxonomy and replay acceptance test.

## Analysis and Adoption

| Item | Pre-specified rule |
|---|---|
| Estimand and comparison | {{paired difference and unit of analysis}} |
| Uncertainty | {{interval/test and resampling unit}} |
| Adoption gate | {{threshold; label it as a design choice, not a result}} |
| Guardrail precedence | {{what happens when primary and guardrails disagree}} |
| Partial outcome | {{how an early stop is reported}} |

## Execution Plan

| Phase | Dates or duration | Output | Budget/owner |
|---|---|---|---|
| {{preflight}} | {{...}} | {{locked inputs and randomization artifact}} | {{...}} |

## Risks and Stopping

| Risk or stop condition | Detection | Response | Effect on conclusion |
|---|---|---|---|
| {{environment drift, budget, data restriction, label disagreement}} | {{...}} | {{...}} | {{...}} |

## Limitations

{{State transfer limits, metadata-only sources, missing causal evidence, and
conditions under which the proposed change must not be adopted.}}

## Sources and Traceability

| Label | Source and date | What it supports | Evidence limit | Frozen location |
|---|---|---|---|---|
| [E1] | {{readable source}} | {{specific claim/design choice}} | {{limit}} | `{{source_path}}`, {{locator}} |

<!-- research-tree:evidence {{chunk_id}} -->

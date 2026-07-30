# Algorithm: intent-constrained recursive research

This document explains the control model behind the scripts. For command shapes
see `SKILL.md`; for persisted objects see `contracts.md`.

## Intent comes first

The user provides an intent, which may contain arbitrary entities, exclusions,
time conditions, audience requirements, and long-tail semantic constraints.
Keep the raw wording as a versioned `IntentProgram`; compile it into clauses
without reducing it to a fixed taxonomy. An unresolved hard clause pauses only
the affected work and asks the smallest discriminating question.

Before recursive research starts, one Intent Analyst produces an explicit
requirements contract. This is a separate preflight, not the first descent
step: it decides what the user actually asked to receive, what supplied
material must be analysed, whether a design must be proposed, which external
questions need research, and what acceptance criteria determine completion.
For example, a request to write an experiment plan from user material requires
material analysis and a feasible plan with controls/measurements; it is not
satisfied by collecting a topical literature summary.

The contract has three states:

```text
pending -> ready                 : research frames may be created
pending -> needs_clarification   : no frame, query, provider call, or research worker
needs_clarification -> pending   : user answers recorded; analyst revises the contract
```

Only a `ready` contract can create `research_frames` or accept `bootstrap`.
`needs_clarification` is reserved for an ambiguity, contradiction, missing
material, time interpretation, audience, success criterion, or similar detail
that would materially change the result. The analyst asks the smallest
decision-discriminating question, rather than guessing. A later clause-level
clarification may block only an existing Frame, but it cannot bypass this
preflight gate.

The original wording is also the first search anchor. It prevents a broad topic
from silently drifting to a more common but different entity.

## The recursive unit

Research advances through this derivation chain:

```text
Frame -> EvidenceVersion -> CognitionVersion -> InformationGap -> ChildFrame
```

A saved page becomes evidence only after an agent accepts it. A cognition cites
one or more evidence spans. A child frame can only be created from a cognition-
backed information gap that names its discriminator and minimum evidence.
Sources and keywords therefore cannot expand the graph directly.

Derivation edges are acyclic and versioned. Semantic links such as `supports`,
`contradicts`, `refines`, and `similar_to` live in the separate relation graph
and may cycle.

## Scheduling, merging, and convergence

The scheduler prioritises expected decision impact, uncertainty reduction,
evidence availability, novelty, and cost. It reserves a bounded budget for
counter-evidence and exploration. Provider choice is a transport decision based
on availability, quota, rate limits, and cost; it is never a topic classifier.

Frames merge only when their focus, information gap, discriminator, applicable
clauses, temporal scope, expected update, and evidence requirement are
equivalent. A potentially useful frame that cannot run within budget is
`deferred_budget`, not pruned. Terminal frames reopen when an Extractor
explicitly links relevant new evidence with `contradicts_cognition_ids` or
`updates_cognition_ids`; wording similarity alone never reopens a frame. Only
affected deferred frontiers are reactivated.

Execution converges when no active frame remains. Argument convergence also
requires every material claim to be supported, contradicted, or explicitly
bounded as insufficient evidence. Budget exhaustion or inaccessible critical
material is reported as partial research, not as successful convergence.

## Collection barrier and worker timing

The first live stage after requirements preflight is coordinator work. Saved
source aggregation is a distinct barrier between collection and review:

```text
intent ready -> open -> acquiring -> aggregating -> reviewing -> extracting -> expanded
                         coordinator    aggregator    reviewers
```

`open -> acquiring` records the intent-constrained query plan. While
`acquiring`, the coordinator must run every enabled provider for every stored
query. It archives each successful provider's original response, records every
provider/query terminal result, deduplicates and balances valid leads across
providers, and materializes the bounded source collection. The raw response
archive, discovery record, saved pages, and source manifest are durable
preconditions for `aggregating`. A captured record keeps the provider(s) that
discovered the lead separate from the transport that captured its page body; a
multi-provider discovery union may legitimately share one controlled capture
transport.

Only `aggregating` creates a Source Aggregator task. It must bind the source
manifest hash, group sources by substantive topic/claim plus context, retain a
primary assessment for every captured page, and preserve cross-cutting pages,
near-duplicates, and contradictions instead of deleting them. It supplies
rationale and rubric components for each source's quality and each topic's
confidence; the service calculates scores and writes the hash-bound aggregation
artifact. Only a verified artifact changes the Frame to `reviewing`.

Only `reviewing` creates research workers: a Source Triager and a Source
Adversary read the same saved collection and aggregation artifact and submit
reviewer-scoped evidence commands. Each must complete, even with an empty
proposal list, before the Frame can enter `extracting`. Low-quality or
non-representative pages require an explicit selection override; adversarial
counterexamples remain visible as contradictions. Reviewers cannot run a fresh
search or source capture. This prevents scheduler fan-out from racing or
bypassing collection provenance or aggregation quality controls.

Extraction consumes the accepted evidence's assessments. The service caps a
cognition's requested confidence by the strongest assessed support from its
source quality, topic confidence, and assessment confidence. This is
deliberately not count-based: more near-duplicate pages do not manufacture a
stronger claim. Low scores become uncertainty, limitations, or a reason for a
new information gap.

## Enforced descent

Frontier ranking is not merely presentation. If `frontier_decision` returns
`descend` because a clear leader has recursive capacity, a terminal `finish`
is rejected. The controller must descend through the selected gap, or a depth,
per-frame call, or global-frame budget must make the decision returnable. A
score tie remains intentionally non-decisive: a selector may return only with
the documented comparative rationale already required by the state model.

## Time and frozen hand-off

`reference_time` anchors relative language. Evidence carries publication,
update, event, and retrieval times; cognitions carry assertion time and a
context signature. The engine audits required temporal fields and requested
ranges before freezing.

Freezing verifies the source aggregation artifacts and registered material
hashes as well as accepted evidence pages. It copies evidence pages, registered
materials, and aggregation artifacts into the snapshot, then builds a corpus
from the copied textual content. The manifest binds the frozen state and every
corpus/material/aggregation artifact by SHA-256. Writers, editor, and Q&A
verify the snapshot before use and may read only it.

Each research chapter receives its frozen source/topic assessments and any
required low-score disclosure. The chapter planner also creates a distinct
intent-deliverable chapter for a required material-analysis or design outcome;
that task receives only the declared material/research chunks plus its design
requirements, acceptance criteria, and assumptions. Writers must distinguish
evidence, material observations, assumptions, and proposed choices. The editor
rechecks citations, assessment-driven limitations, and the actual fulfilment of
design/material requirements; failures become repair tasks, not polished but
unsupported prose. A question that needs material outside the snapshot starts a
new intent version or research run.

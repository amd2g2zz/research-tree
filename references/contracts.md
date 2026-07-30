# Research State Contracts

`scripts/engine.py` is the only writer of live recursive state. Subagents return
proposal packages; they never mutate the graph.

## IntentProgram

```jsonc
{
  "version": 1,
  "raw": "Find recent deep-learning material, excluding university courses",
  "created_at": "2026-07-29T00:00:00+00:00",
  "clauses": [{
    "id": "c1", "raw": "excluding university courses",
    "strength": "hard", "scope": ["source", "report"],
    "evaluator": "semantic",
    "status": "enforced|ambiguous|conflicted|blocked_on_user|missing_input|assumed"
  }]
}
```

`reference_time` is fixed at intent creation. Relative ranges must preserve both
the resolved range and the field being evaluated (`published_at`, `updated_at`,
or `event_at`).

## Intent contract and registered materials

Every newly initialized state has an `intent_contract` in `pending` state. No
Frame, query plan, provider call, or research worker is admissible until an
Intent Analyst records a `ready` contract. The analyst may instead return
`needs_clarification`; its blocking questions stop all research work until the
user's answers are recorded and a revised analysis is submitted.

```jsonc
{
  "intent_contract": {
    "schema": 1,
    "status": "pending|needs_clarification|ready",
    "version": 2,
    "contract": {
      "summary": "Produce a feasible experiment plan from the supplied protocol.",
      "deliverables": [{
        "id": "experiment-plan", "kind": "experiment_plan",
        "description": "A complete, feasible experimental protocol",
        "required": true,
        "requires_research": true,
        "requires_material_analysis": true,
        "requires_design": true,
        "research_frame_refs": ["measurement-evidence"]
      }],
      "research_questions": ["Which controls and measurements are justified?"],
      "decision_questions": [{
        "id": "adoption", "question": "Should the change be approved now?",
        "why_it_matters": "This controls implementation commitment.",
        "impact": "high", "deliverable_ids": ["experiment-plan"]
      }],
      "design_requirements": ["include controls and feasibility limits"],
      "writing_requirements": ["write for the lab team"],
      "acceptance_criteria": ["state controls, measurements, and decision rule"],
      "assumptions": ["..."],
      "other_constraints": ["..."],
      "user_materials": [{
        "material_id": "protocol-note", "status": "provided|missing|optional",
        "description": "...", "intended_use": "...", "required": true,
        "registered": {"local_path": "materials/protocol.md", "sha256": "..."}
      }],
      "clarifying_questions": [{
        "id": "target-system", "question": "...", "why": "...", "blocking": true
      }],
      "research_frames": [{
        "contract_ref": "measurement-evidence",
        "focus": "External evidence for measurements, controls, and decision rules",
        "information_gap": "Which measurements and controls are feasible and justified?",
        "discriminator": "Saved sources that state a method, control, or limitation",
        "expected_update": "Bound the experiment design choices",
        "evidence_requirement": "Cited saved external evidence"
      }]
    },
    "questions": [],
    "answers": {}
  },
  "materials": {
    "protocol-note": {
      "material_id": "protocol-note", "local_path": "materials/protocol.md",
      "sha256": "...", "byte_count": 1234, "media_type": "text/markdown",
      "text_extractable": true
    }
  }
}
```

`provided` material ids must have been registered with an existing
workspace-relative file. They may be registered at `engine init`, or added or
replaced while the contract is `pending` or `needs_clarification`:

```bash
uv run python scripts/engine.py register-material --material @material.json
uv run python scripts/engine.py register-material --material @replacement.json --replace
```

The argument is one material object. Registration records the file hash, size,
media type, and whether it is directly text-extractable; freeze rejects a
missing or changed file. Once the contract is `ready`, registration is rejected
so a planned deliverable cannot receive an unreviewed input. The current direct
text path supports only `.md`, `.txt`, and `.html`. A PDF or DOCX can remain a
verified frozen artifact, but it cannot satisfy a required material-analysis
deliverable until an explicit extraction produces and registers a textual
workspace material. The system must not claim that such a file was analyzed
merely because it was copied into a snapshot.

A `ready` contract cannot retain a blocking question, a required missing
material, or a required material-analysis deliverable without at least one
provided material. Only research questions that need external saved evidence
should produce `research_frames`; the contract may require material analysis or
design without inventing a search frame. A required research deliverable must
resolve to one or more declared `research_frame_refs`. Each declaration has a
unique `contract_ref`; that reference and its derived `deliverable_ids` are
stored on the durable Frame. Omitted references mean all declared frames are
bound for compatibility, not that no research is required. Freeze rejects a
required research deliverable with no bound terminal Frame containing a cited
cognition.

While status is `needs_clarification`, recording only part of the question set
keeps that status. All listed questions must be answered and a revised contract
must be submitted before the contract can become `ready`.

### Decision closure

`decision_questions` is optional for legacy frame-only runs. When present, the
runtime creates a pending `decision_synthesis` record and will not freeze until
each question is assessed. The assessment status is one of
`supported`, `conditional`, `gap_child`, `need_user_input`, or `insufficient`.
Every assessment names its supporting/refuting cognition ids, any gap or user
question, the conditions that would change the conclusion, and an action. A
high-impact question must be `supported` before `recommendation: approve` is
accepted. Exact numbers, thresholds, budgets, sample sizes, and operating rules
must appear in `parameter_provenance` with one of these bases:
`user_constraint`, `direct_evidence`, `transfer_method`, `assumption`, or
`need_user_input`.

During extraction, a decision-aware Frame also stores `evidence_coverage`.
Every accepted evidence id gets exactly one disposition: `cited`,
`context_only`, `needs_followup`, or `excluded`, with a rationale. `cited` must
be used by a cognition; `needs_followup` must point to a gap created in the same
extraction package. This preserves selected sources that do not become prose
claims and makes their treatment auditable.

## Frame and derivation DAG

```jsonc
{
  "id": "f_0001_...", "focus": "...",
  "contract_ref": "measurement-evidence", "deliverable_ids": ["experiment-plan"],
  "information_gap": "...", "discriminator": "...",
  "expected_update": "...", "evidence_requirement": "...",
  "intent_clause_ids": ["c1"], "trigger_cognition_ids": ["k_..."],
  "constraint_env": [], "temporal_scope": {"field": "published_at"},
  "depth": 0,
  "state": "open|acquiring|aggregating|reviewing|extracting|expanded|resolved|contradicted|...",
  "collection": {
    "discovery_path": "research_drift/discovery/<frame>.json",
    "source_manifest_path": "research_drift/sources/<frame>.json",
    "request_sha256": "...",
    "source_manifest_sha256": "..."
  },
  "aggregation": {
    "status": "pending|complete",
    "path": "research_drift/aggregation/<frame>.json",
    "sha256": "...",
    "source_manifest_sha256": "...",
    "summary": {"cluster_count": 2, "source_count": 5},
    "clusters": []
  },
  "review": {
    "expected_roles": ["source_triager", "source_adversary"],
    "completed_roles": []
  }
}
```

Only `Frame -> Evidence -> Cognition -> Gap -> ChildFrame` edges form the
recursive DAG. `supports`, `contradicts`, `refines`, and `similar_to` are stored
in `relations` and may form cycles.

`descent_policy` is durable state, with global `max_depth`, `max_frames`,
per-frame `max_calls_per_frame`, a `score_margin`, and a low-confidence return
threshold. These cap new work but leave unselected gaps in `frontier` as
`deferred`; score ties require a documented selector decision rather than a
heuristic prune.

## Saved-source aggregation

`collection_ready` verifies the raw discovery/source manifest/pages and moves a
Frame from `acquiring` to `aggregating`. It does not create review workers.
Exactly one Source Aggregator submits an `aggregate_sources` command bound to
the current `source_manifest_sha256`; host workflow commands additionally
require `aggregator_role: "source_aggregator"`. The service writes a hash-bound
artifact under `research_drift/aggregation/` and moves the Frame to `reviewing`
only after all captured pages have been assessed.

```jsonc
{
  "frame_id": "f_...",
  "source_manifest_sha256": "...",
  "quality_rubric": {
    "version": "quality-v1",
    "weights": {
      "authority": 0.25, "directness": 0.20, "traceability": 0.20,
      "temporal_fit": 0.15, "capture_completeness": 0.10, "independence": 0.10
    }
  },
  "topic_confidence_rubric": {
    "version": "topic-confidence-v1",
    "weights": {
      "source_quality": 0.30, "corroboration": 0.20, "independence": 0.20,
      "temporal_coherence": 0.15, "scope_match": 0.15
    }
  },
  "clusters": [{
    "topic_key": "measurement-validity", "topic": "...",
    "context_signature": "...", "dedup_rationale": "...",
    "representative_local_paths": ["research_drift/pages/a.md"],
    "confidence_components": {
      "source_quality": 0.8, "corroboration": 0.7, "independence": 0.6,
      "temporal_coherence": 0.9, "scope_match": 0.8
    },
    "confidence_score": 0.76, "confidence_rationale": "...", "unresolved": [],
    "sources": [{
      "local_path": "research_drift/pages/a.md", "content_sha256": "...",
      "relation": "representative|corroborating|near_duplicate|contradictory|irrelevant",
      "primary": true,
      "quality_components": {
        "authority": 0.9, "directness": 0.8, "traceability": 0.9,
        "temporal_fit": 0.8, "capture_completeness": 1.0, "independence": 0.7
      },
      "quality_score": 0.85, "assessment_confidence": 0.8, "rationale": "..."
    }]
  }]
}
```

The agent supplies reasoned components; the service calculates both scores.
Deduplication is semantic/topic-aware, not a URL/title collapse. Every captured
page must occur in exactly one `primary: true` topic assessment, but may occur
in additional non-primary clusters. A representative prioritizes downstream
review and never deletes a captured near-duplicate or contradiction.

## Evidence and cognition

```jsonc
{
  "evidence": {"id": "e_...", "local_path": "research_drift/pages/x.md",
               "content_hash": "sha256", "published_at": "...", "event_at": "...",
               "discovery_providers": ["openalex", "anysearch"],
               "capture_provider": "anysearch",
               "aggregation_assessment": {
                 "topic_key": "...", "quality_score": 0.8,
                 "cluster_confidence": 0.7, "assessment_confidence": 0.9,
                 "relation": "representative", "representative": true
               },
               "capture": {"status": "complete|possibly_truncated",
                           "method": "anysearch.extract", "character_count": 123,
                           "limit_chars": 50000}},
  "cognition": {"id": "k_...", "claim": "...",
                "claim_key": "stable claim identity", "polarity": "supports|refutes|unknown",
                "context_signature": "model family / metric / scope",
                "asserted_at": "...", "evidence_time": "...",
                "confidence_requested": 0.9, "confidence_cap": 0.72,
                "confidence": 0.72,
                "evidence_assessment": {"confidence_cap": 0.72, "clusters": []},
                "source_spans": [{"evidence_id": "e_...", "locator": "p:4"}]}
}
```

An accepted evidence item requires locally saved source content that is a
`captured` record in this Frame's current source manifest, with the same
SHA-256 content hash and a completed primary aggregation assessment. Evidence
commands are accepted only in `reviewing` and must name one of the two pending
review roles. Both roles may submit an empty selection, but both must complete
before `extracting` begins. Selecting a low-quality or non-representative page
requires `selection_override_rationale`; this keeps a contradiction or
limitation auditable instead of pretending that it is equally strong support.
A cognition requires at least one evidence span with a stable locator. Its
requested confidence is capped from the strongest relevant assessed support
(source quality, cluster confidence, and assessment confidence), rather than
being amplified by the count of near-duplicate pages. A
`possibly_truncated` capture may support only spans within the saved content;
it does not establish that omitted page content was reviewed. Extractors may set
`contradicts_cognition_ids` or `updates_cognition_ids` on a new cognition;
updates are accepted only when `evidence_time` is strictly newer. The engine
records these as semantic relations and reopens only affected terminal frames
when deferred frontier gaps exist.

An Extractor may atomically introduce a cognition and its resulting gap by
using a batch-local reference. Give the cognition a unique `proposal_ref`, then
put that value in the gap's `trigger_cognition_refs`. The engine resolves it to
the newly generated durable cognition ID before validating the gap. Existing
`trigger_cognition_ids` remain for cognitions already persisted in the same
frame; proposal refs never become durable IDs and cannot reference another
frame or extraction batch.

## Frozen snapshot

`research_snapshots/<id>/manifest.json` records SHA-256 values for
`research_state.json` and every corpus file. The state retains each accepted
evidence hash, while `frozen_evidence_paths` maps it to a copied page under
`research_snapshots/<id>/pages/`. `frozen_materials` maps every registered
material to a copied, hash-bound artifact under `pages/materials/`; textual
material may have citable corpus chunks, while non-textual material remains a
verified input with no invented text citation. `frozen_aggregation_paths` and
`aggregation_sha256` bind each completed aggregation artifact copied under
`aggregation/`. Freeze rejects an invalid collection aggregation or changed
registered material. Q&A, writers, and editors validate all of these values
before retrieval.

The chapter plan binds an `evidence_assessment` hash to every research-frame
chapter. It carries source quality, topic confidence, citable status, and
required disclosures for low-score or unassessed evidence. A ready intent
contract also creates `intent_deliverable` chapters for required
material-analysis or design work. These contracts bind permitted material and
research chunks, delivery requirements, acceptance criteria, and assumptions.
An intent-deliverable selects research inputs only from its
`research_frame_refs`/`contract_ref` binding. It additionally carries a
`delivery_checklist` and `input_use_requirements`: design requirements,
acceptance criteria, required material inputs, and required research inputs are
turned into stable check IDs. A writer places a matching marker such as
`<!-- research-tree:check design-1 -->` in the chapter and, where the required
input has citable chunks, cites at least one permitted chunk from that input.
The marker is an auditable coverage declaration, not a substitute for semantic
editor review. A missing check or a missing required-input citation rejects the
chapter; report compilation revalidates the same obligations. Chapter manifests
and the report manifest bind the assessment/disclosure, delivery-contract, and
delivery-verification hashes; the editor packet turns violations into repair
tasks rather than compiling them away.

Q&A is a frozen-snapshot-only capability. It validates the snapshot and returns
only cited frozen chunks; it cannot search, add evidence, change requirements,
or answer from the live workspace.

## Discovery and host hand-off

`research_drift/discovery/<frame-id>.json` is a cache of provider lead batches,
bound to the stored query plan and provider policy. It contains one terminal
record for every selected provider/query pair. Each successful record points to
the exact archived provider response under
`research_drift/discovery/raw/<frame>/<request-sha256>/`, with byte count,
character count, and SHA-256. A missing or altered raw file invalidates the
cache and requires discovery to run again. It is not evidence and cannot be
cited by a cognition.

`research_drift/sources/<frame-id>.json` records every balanced candidate as
`captured`, `failed`, or `deferred_budget`. Every `captured` record binds the
saved page and content hash. It also records `discovered_by` (every search
provider that produced the lead) separately from `capture_provider` (the page
body transport); `summary.origin_coverage` reports the resulting balance.
`discovery_providers`/`discovered_by` establish the multi-provider discovery
origin. `capture_provider` establishes only how the selected content was
acquired. In the bundled flow, substantive arXiv, OpenAlex, or Crossref
metadata can be captured through the originating provider and is marked
`metadata_limited` / `full_text: false`; short or absent metadata falls back
to the fixed AnySearch page transport. Do not use a shared capture provider as
a proxy for common discovery origin, full-text completeness, or source
independence.
Missing or altered captured pages invalidate that manifest and require
materialisation again. `source_acquirer.py extract`
accepts a public HTTPS URL, calls the fixed AnySearch endpoint, writes a
generated filename in the page store, and returns an evidence proposal only.
`host_adapter.py acquire-source` exposes the same coordinator-only capture
boundary. Graph changes remain idempotent command objects; chapter/report
submission has separate fixed-path operations that revalidate the frozen
snapshot and allowed chunk citations.

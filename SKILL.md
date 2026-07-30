---
name: research-tree
description: Intent-constrained deep research. It first turns ambiguous requests and registered user materials into an executable requirements contract, then recursively grows an auditable evidence DAG and freezes a cited snapshot for writing and Q&A.
---

# research-tree

## Purpose

The user supplies an **intent**, not a pre-built research tree. The intent can
contain arbitrary long-tail constraints: entities, exclusions, style, audience,
time, scope, success criteria, and user-specific material. Preserve them as
versioned clauses rather than trying to enumerate them as fields.

Before any Frame, query, or network call, an Intent Analyst turns that raw
request into an explicit requirements contract. It distinguishes the requested
deliverables, external research questions, supplied-material analysis, design
requirements, writing requirements, acceptance criteria, assumptions, and
blocking ambiguity. A request such as "use my materials to write an experiment
plan" is therefore not reduced to a research report: the contract can require
material analysis and a feasible experiment-plan deliverable, while creating
research Frames only for the external questions that genuinely need evidence.
For a decision-bearing request, the contract must also contain explicit
`decision_questions`. These are the actions the user may approve, reject, defer,
or redesign after research, each with impact and rationale. A report is not
ready merely because its chapters and citations are complete: every such
question must be synthesized into a bounded conclusion, evidence chain,
conditions that would change it, and next action.

Research recursively follows this path:

```text
IntentProgram -> Frame -> locally saved Evidence -> cited Cognition
              -> InformationGap -> ChildFrame
```

The recursive DAG contains only those derivation edges. Supporting, refining,
contradicting, and similar relationships are recorded separately and may cycle.

## Recursive Descent Control

This is recursive descent, not exhaustive recursive expansion. Each Frame is a
procedure with a return contract. After extraction, its candidate gaps enter a
deferred frontier. A Branch Selector receives the ranked frontier and either
selects one blocking gap for a child call or returns the Frame. The parent then
waits; a Reducer explicitly returns the child's terminal result to the parent.
Unselected gaps remain deferred and are revisited only after low confidence,
contradictory evidence, or a temporal/source change. The score combines declared
information gain and acquisition cost with evidence uncertainty, novelty,
constraint coverage, and temporal pressure. `max_depth`, `max_frames`, and
`max_calls_per_frame` bound termination without deleting deferred alternatives.
When the leading scores are within `score_margin`, the selector must document a
comparative choice or return; the heuristic does not silently prune a tie.
When a frontier has a clear leader and recursive capacity remains, `finish`
rejects the terminal return. The selector must make the descent or an explicit
budget/depth limit must make returning valid.

The only scheduled activity while the intent contract is `pending` is one
Intent Analyst task; no Frame or search exists yet. If the contract is
`needs_clarification`, the coordinator asks its recorded minimal blocking
questions and waits for answers. Once it is `ready`, the coordinator compiles
the query plan, runs every enabled provider, archives every successful provider
response, materializes a bounded cross-provider source set, and records its
manifest. `uv run python scripts/research_orchestrator.py --discover --write`
performs that collection stage.

Collection transitions a Frame to `aggregating`, not directly to review. At
that point exactly one Source Aggregator receives the hash-bound saved
collection and produces semantic topic clusters, representative selections,
and rubric components for source quality and topic confidence. Only after that
aggregation artifact validates does the Frame enter `reviewing` and the host
may fan out Source Triager and Source Adversary tasks. Extraction, selection,
and reduction remain downstream of both reviews. No worker may mutate the
graph directly.

## Ownership

| Role | Owns | Must not do |
|---|---|---|
| Intent Analyst subagent | Requirements contract: deliverables, materials, design/writing needs, acceptance criteria, blocking questions, and only necessary research Frames | Search, fabricate user material, or create a query plan |
| Coordinator | Clarification hand-off, query-plan hand-off, multi-provider discovery, raw-response archive, bounded source materialisation | Interpret evidence or create a research child |
| Source Aggregator subagent | Hash-bound semantic topic clustering, source-quality and topic-confidence rationale for the saved collection | Search, fetch URLs, discard captured sources, accept evidence, or modify graph state |
| Source Triager subagent | Select suitable evidence only from the completed aggregation and saved collection | Search, extract URLs, or modify graph state |
| Extractor subagent | Immutable cognition/gap proposal package with source locators | Modify graph state |
| Source Adversary subagent | Counter-evidence and alternative-explanation proposals from the completed aggregation and saved collection | Search, extract URLs, erase evidence, or modify graph state |
| Writer subagent | One frozen chapter, including material-analysis or design deliverables when contracted | Use live evidence, another writer's file, or silently strengthen low-score evidence |
| Decision Synthesizer subagent | One frozen pre-publication decision synthesis covering every `decision_question`, source disposition, gap, and parameter basis | Search, create frames, or turn conditional evidence into approval |
| Editor subagent | One draft and the final `report.md` compiled from all submitted chapters and the reviewed decision synthesis | Invent facts or silently compile unmet material/design requirements |
| Senior-user Reviewer subagent | Independent structured review of the editor draft: evidence -> inference -> action, gaps, and parameter provenance | Search, edit research state, or replace the editor's report |
| Q&A subagent | Cited answers from a frozen snapshot | Fetch live web data or modify research state |

## Project layout

```text
<project>/
├── research_project.json
├── research_providers.json      # transport/cost policy, never semantic routing
├── research_drift/
│   ├── research_state.json      # live versioned intent and recursive DAG
│   ├── drift_log.jsonl
│   ├── pages/                   # captured source content
│   └── aggregation/             # hash-bound topic/quality assessments
├── research_snapshots/<id>/
│   ├── research_state.json      # immutable frozen state
│   ├── aggregation/             # copied, verified aggregation artifacts
│   ├── pages/materials/         # copies of registered user material
│   └── corpus/                  # frozen chunks, vectors, inverted index
├── research/chapters/
├── research/editor/
├── report.md                    # default deliverable
└── deliverables/                # optional PDF only
```

## 1. Initialise intent, register materials, and negotiate requirements

The Python runtime is managed by `uv`. Run `uv sync --locked` before invoking
the scripts. The execution controller in `scripts/langgraph_runner.py` is
optional: it can schedule/resume work, but `research_domain.py` remains the
authority for DAG invariants, evidence, and freeze eligibility. Supply a
durable LangGraph checkpointer in production; every resumed mutation must carry
a stable `command_id` and is applied through `ResearchService`.

```bash
uv run python scripts/project.py init --intent "<user intent>"
uv run python scripts/engine.py init --intent "<user intent>" \
  --reference-time "<ISO-8601 request time>" \
  --clauses '[{"id":"c1","raw":"...","strength":"hard","status":"enforced"}]' \
  --materials @materials.json
```

`--materials` is optional. When the user supplied files matter to the result,
register each existing workspace-relative file before intent analysis, rather
than passing an untracked path to a writer later:

```json
[
  {
    "id": "protocol-note",
    "path": "materials/protocol.md",
    "description": "The user's current protocol draft",
    "media_type": "text/markdown"
  }
]
```

Registration records a content hash, size, and media type. A contract may call
a material `provided` only when the same id is registered. Freeze rechecks the
live file hash and copies registered materials into the snapshot, so changing a
file after preflight cannot silently change a planned deliverable.

When a material arrives while requirements are still being negotiated, register
or replace it before the contract becomes `ready`:

```bash
uv run python scripts/engine.py register-material --material @material.json
uv run python scripts/engine.py register-material --material @replacement.json --replace
```

`--material` is one material object, not an array. Registration is allowed only
while the contract is `pending` or `needs_clarification`; a ready contract must
not acquire a silent new input. Only `.md`, `.txt`, and `.html` materials are
currently text-extractable for required material analysis. A PDF or DOCX may be
registered and frozen as a hash-bound input, but it is not treated as analyzed
text. If it is required for analysis, explicitly extract it to a registered
workspace text file before submitting a ready contract.

Set `reference_time` once. Interpret relative time such as “recent three years”
against that fixed instant. Preserve every clause verbatim; an unknown constraint
may use the `semantic` evaluator rather than being discarded.

Every newly initialized run starts with an intent contract in `pending` state.
Run `engine next`, or write the orchestrator batch, to obtain exactly one
`intent_analyst` task. It must submit a contract through `analyze-intent`:

```bash
uv run python scripts/engine.py analyze-intent --contract @intent-contract.json
```

The contract records `deliverables`, `research_questions`,
`design_requirements`, `writing_requirements`, `acceptance_criteria`,
`user_materials`, `clarifying_questions`, and optional `research_frames`. A
`ready` contract contains no blocking question and may create its declared
research Frames. A `needs_clarification` contract blocks all Frame creation,
discovery, and research workers. Ask only the listed questions, record the
answers, and request a revised analysis:

```bash
uv run python scripts/engine.py answer-intent --answers @intent-answers.json
uv run python scripts/engine.py analyze-intent --contract @revised-intent-contract.json
```

For every required deliverable with `requires_research: true`, bind the
deliverable to the relevant declared frames with `research_frame_refs`. Each
referenced `research_frames` entry has a unique `contract_ref`; the durable
Frame carries that `contract_ref` and derived `deliverable_ids`. This keeps an
experiment plan, for example, from consuming unrelated frozen research merely
because it exists in the snapshot. Explicit references are preferred. Omitting
them means all declared frames are bound, not that external research is absent.
The freeze audit rejects a required research deliverable that has no bound
terminal Frame with a cited cognition.

If the user answers only some blocking intent questions, the contract remains
`needs_clarification`. It cannot become ready or start discovery until every
listed question is answered and the analyst records a revised contract.

Frame-level clause clarification still uses `engine clarify` later in the run;
it is not a substitute for resolving preflight requirements ambiguity.

## 2. Bootstrap and recurse after the contract is ready

The original user wording is a valid first-search anchor. For “investigate
DeepMind”, the first material must be about DeepMind. Compile each query plan
from explicit user anchors, the active Frame's information gap, local cognition,
applicable clauses, and its temporal scope.

```bash
uv run python scripts/engine.py bootstrap --frames '[{
  "focus": "...",
  "information_gap": "...",
  "discriminator": "what would distinguish explanations",
  "expected_update": "what changes if answered",
  "evidence_requirement": "minimum adequate evidence"
}]'
```

Manual `bootstrap` is accepted only after the contract is `ready`. For every
open Frame, follow `engine next`:

1. `formulate`: submit a JSON query plan with `engine formulate`.
2. `discover_and_materialize`: run every globally eligible provider for the plan with
   `research_orchestrator.py --discover --write`. Providers are
   execution choices only: cost, rate limit, anti-bot risk, and concurrency. Do
   not classify the research topic to select a provider.
   Each provider/query pair receives a terminal record even if another provider
   fails. Successful provider bodies are saved under `discovery/raw/`; no
   normalized lead without its raw response is materialized. The coordinator
   deduplicates and round-robins valid cross-provider leads, saves the bounded
   resulting pages under `research_drift/pages/`, and records `captured`,
   `failed`, or `deferred_budget` for every candidate in `sources/<frame>.json`.
   `discovery_providers` and `discovered_by` record every engine that found a
   lead; `capture_provider` records the transport that saved its content. They
   answer different questions. Substantive arXiv, OpenAlex, and Crossref
   summaries/abstracts may be materialised through their native provider
   capture path, explicitly marked `metadata_limited` and `full_text: false`;
   short or unavailable metadata falls back to controlled AnySearch page
   extraction. A common capture provider is never evidence of a single search
   origin or of source independence.
3. `aggregate_saved_sources`: after the manifest exists, start exactly one
   Source Aggregator. It clusters by substantive topic/claim and context, not
   URL or title; scores source quality and topic confidence from rationale and
   rubric components; and preserves every captured source. Each captured page
   receives exactly one primary topic assessment, though a cross-cutting page
   may appear in additional clusters. Representatives only prioritize review;
   near-duplicates and contradictions remain visible. The aggregator binds the
   exact source-manifest SHA-256 and writes
   `research_drift/aggregation/<frame>.json`. A host worker must submit
   `aggregator_role: "source_aggregator"`; the direct CLI equivalent is:

   ```bash
   uv run python scripts/engine.py aggregate-sources --frame "<frame-id>" \
     --clusters @topic-clusters.json --source-manifest-sha256 "<manifest-sha256>"
   ```
4. `review_saved_sources`: only after validated aggregation exists, start one
   Source Triager and one Source Adversary. Both read only archived search
   records, the source manifest, aggregation artifact, and saved pages. Each
   submits exactly one `evidence` command with its `reviewer_role`, using an
   empty list when no page qualifies. A low-quality or non-representative
   selection needs `selection_override_rationale`; a counterexample remains a
   contradiction, not a duplicate. The Frame cannot enter `extracting` until
   both reviewer roles complete. A submitted page must be a `captured` entry in
   that Frame's source manifest and still match its recorded content hash. A
   URL/snippet without locally saved content is always a lead, not evidence.
   An AnySearch extract at its 50,000-character boundary is marked
   `possibly_truncated` and can support only cited captured passages, not a
   claim that the complete original page was read.
5. `extract`: after the review barrier, have an Extractor submit cognitions with `evidence_id + locator`
    and their candidate information gaps. When a gap depends on a cognition
    created in the same atomic package, give the cognition a unique
    `proposal_ref` and put it in the gap's `trigger_cognition_refs`; use
    `trigger_cognition_ids` only for already persisted cognitions in the frame.
    The service caps a cognition's requested confidence by its strongest
    applicable source-quality, topic-confidence, and assessment-confidence
    support. Repeated near-duplicates cannot raise that cap. When the intent
    contract has `decision_questions`, submit `coverage` for every accepted
    `evidence_id` exactly once: `cited`, `context_only`, `needs_followup`, or
    `excluded`, with a rationale. `cited` must appear in a cognition; any
    `needs_followup` must point to a gap created in the same package. This is
    the explicit source-disposition record that prevents a selected source
    from disappearing between aggregation and writing.
6. Admit a child only when its gap can change a decision/cognition, has a
   discriminator and verification path, respects inherited clauses, and is not
   equivalent to an existing Frame. Use `engine descend` with an explicit
   selection rationale; `engine expand` is only a compatibility shortcut.
7. Use `engine finish` with `resolved`, `contradicted`, `gap_user_input`,
   `deferred_budget`, or another terminal state to return a bounded result.
   It is rejected while a clear ranked frontier leader still has descent
    capacity; score ties may return only under their documented comparison.

Do not create a child directly from a source or a keyword. It must be reached
through an auditable cognition and information gap.

When no active Frame remains, a decision-aware run schedules exactly one
`decision_synthesizer` task before freeze. Submit it with:

```bash
uv run python scripts/engine.py synthesize-decision --synthesis @decision-synthesis.json
```

The synthesis must assess every decision question as `supported`, `conditional`,
`gap_child`, `need_user_input`, or `insufficient`, and include the cognition or
gap ids, conditions that would change the conclusion, and an action. A high-
impact question that is not `supported` forbids `recommendation: approve`.
Every consequential number or operating rule belongs in
`parameter_provenance` with a basis of `user_constraint`, `direct_evidence`,
`transfer_method`, `assumption`, or `need_user_input`.

## Time and contradiction discipline

Every evidence item tracks `published_at`, `updated_at`, `event_at`, and
`retrieved_at` when available. Every cognition has `asserted_at`,
`evidence_time`, and `context_signature`. A statement that is true under a new
model family, metric, date, or operating range is not automatically a
contradiction of an earlier statement.

Extractors can explicitly set `claim_key`, `polarity`,
`contradicts_cognition_ids`, or `updates_cognition_ids`. The engine requires a
strictly newer `evidence_time` for an update, records the relation, and reopens
only an affected terminal Frame with deferred work. It never infers a
contradiction from lexical overlap alone.

When a claim changes over time, create a Frame to explain whether evidence,
definitions, measurement, scope, or conditions changed. Never flatten a history
such as “effective -> ineffective -> effective” into a timeless yes/no answer.

## Convergence and pruning

Graph-derived centrality is not a convergence rule. It may help organise a final report, but
does not decide what to research next. Schedule Frames by expected uncertainty
reduction, decision impact, evidence availability, novelty, and cost. Reserve
some budget for counter-evidence.

- `pruned_irrelevant`: duplicate, covered, unrelated, or unverifiable with no
  possible user/material recovery.
- `deferred_budget`: potentially valuable but not affordable now; retain a
  reopening condition.
- `gap_user_input`: only the user can supply the discriminating material.

The run is ready to freeze only when no active Frame remains and all key claims
are supported, contradicted, or explicitly unresolved. Budget exhaustion is
`partial`, not convergence.

## Freeze, write, and answer questions

Q&A and writing are unavailable during live research. First freeze:

```bash
uv run python scripts/project.py freeze --snapshot <snapshot-id>
uv run python scripts/project.py chapter-plan --snapshot <snapshot-id>
uv run python scripts/research_orchestrator.py --snapshot <snapshot-id> --write
```

Freeze performs temporal and content-hash evidence checks, validates every
completed source-aggregation artifact and registered material hash, copies
accepted pages/materials/aggregation artifacts into the snapshot, and builds
its corpus from the copied textual content. The manifest binds the frozen state,
corpus, materials, and aggregation artifacts with SHA-256; readers validate it
before use. Each writer receives exactly one chapter contract and only reads
that snapshot. Eight chapters therefore produce eight independent writer tasks,
not one writer asked to cover eight topics. The plan contains normal
research-frame chapters plus an intent-deliverable chapter whenever the ready
contract requires material analysis or design (for example, an experiment
plan). Then create the editor packet:

The frozen writer batch sets `max_parallel` to the number of ready chapter
tasks. Provider discovery's `policy.max_parallel` is a separate limit and must
not be reused for writing. If a chapter depends on another chapter, its writer
is deferred until every `dependency_chapter_id` is ready; the batch records
those deferred chapters instead of launching a worker that is guaranteed to be
rejected. This preserves one writer per chapter while allowing independent
chapters to fan out together.

```bash
uv run python scripts/project.py editor-packet --snapshot <snapshot-id>
```

Writers return prose through the fixed delivery boundary, never by choosing an
output path. A chapter contract carries allowed chunks, its source/topic
assessment, any required low-score disclosure, and the design/material
acceptance criteria. Writers must distinguish frozen material observations,
cited research, assumptions, and proposed design choices; they must not turn a
low-quality source or low-confidence topic into a decisive claim. Each
submitted chapter is rechecked against the frozen chunk allowlist and its
quality/delivery contract. The editor receives the same assessment and must
return repair tasks for missing disclosures, unsupported confidence, or unmet
material/design requirements rather than compiling them away. The editor then
creates a draft, an independent senior-user reviewer checks it, and the editor
performs the final compilation:

```bash
uv run python scripts/project.py submit-chapter --snapshot <snapshot-id> --chapter <chapter-id> --content @draft.md
uv run python scripts/project.py stage-report --snapshot <snapshot-id> --content @editor-draft.md
uv run python scripts/project.py submit-report-review --snapshot <snapshot-id> --content @editor-draft.md --assessment @report-review.json
uv run python scripts/project.py compile-report --snapshot <snapshot-id> --content @editor-draft.md
```

The editor must produce a reader-facing report, not a compressed concatenation
of chapters. For an `experiment_plan` or material-backed design, the editor
packet declares the `experiment_plan` presentation profile: decision summary,
evidence judgment, protocol, metrics/adjudication, analysis/adoption rules,
execution plan, risks/stopping, limitations, and a readable source ledger are
required. Use labels such as `[E1]` in visible prose and retain frozen chunk
identifiers in HTML comments or a technical trace appendix. A generic report
that exposes `[citation: c_...]` prose or omits the required structure is
rejected at compilation. For a decision-aware snapshot, the draft must bind the
decision-synthesis hash, every decision-question id, and every parameter
provenance id. Compilation also requires an approved review bound to the same
draft hash and frozen synthesis; the review is a gate, not a replacement for
the editor.

An `intent_deliverable` chapter also carries a `delivery_checklist` and
`input_use_requirements`. Put one provenance marker for every checklist item
where its coverage is discussed:

```markdown
<!-- research-tree:check design-1 -->
<!-- research-tree:check acceptance-1 -->
<!-- research-tree:check material-protocol-note -->
```

The marker is a coverage declaration, not proof that the prose is correct; the
editor still evaluates the substantive requirement. For each required material
or bound research input that has citable chunks, cite at least one of that
input's allowed frozen chunk IDs. `submit-chapter` rejects a missing marker or
required-input citation, and `compile-report` verifies them again. These checks
therefore cannot be bypassed by a report-level summary. They occur after a
snapshot exists; the pre-freeze counterpart is the binding/cited-terminal-frame
audit above.

The dedicated Q&A subagent uses only frozen evidence:

```bash
uv run python scripts/qa.py ask --snapshot <snapshot-id> --question "..."
```

It must cite returned `chunk_id` and `source_path`, state the frozen time for
time-sensitive answers, and return `partial` or `unknown` instead of extending
research. A new question outside the snapshot begins a new intent or research run.

The default output is `report.md`. Generate a PDF only if the user explicitly
requests it, then invoke `lovstudio-any2pdf` on the frozen report.

## Claude Code and Codex hosts

For a host-managed worker pool, use `scripts/host_adapter.py`. It writes a
host-scoped task batch and accepts only structured DAG commands, fixed chapter
or report artifacts, or frozen Q&A retrieval. It never executes a worker-supplied
shell command or writes a worker-selected path.

```bash
uv run python scripts/host_adapter.py dispatch --host codex --discover
uv run python scripts/host_adapter.py dispatch --host claude-code --snapshot <snapshot-id>
uv run python scripts/host_adapter.py dispatch --host codex --snapshot <snapshot-id> --question "..."
```

The host hand-off includes separate `stage-report`, `submit-report-review`,
and `compile-report` routes. The first and last are editor-owned; the review
route is reserved for the independent senior-user reviewer.

Optional repository-local lifecycle observer templates are in
`hooks/claude-code.settings.template.json` and
`hooks/codex.hooks.template.json`. Their static hooks record minimal lifecycle
events and a read-only `Stop` task summary only. They must not be turned into
auto-search, auto-submit, or permission-bypass hooks.

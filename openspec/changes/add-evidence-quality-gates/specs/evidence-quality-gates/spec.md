# add-evidence-quality-gates Specification Delta

## ADDED Requirements

### Requirement: Stage outcome carries the four separated facts

Every research stage SHALL persist a structured `StageOutcome` in
`parallel_stages.outputs` that separates (1) search execution, (2) per-source
relevance verdicts with a stated basis, (3) evidence sufficiency, and (4)
findings with explicit unresolved claims. Legacy bare-artifact rows SHALL be
migrated to `execution: "executed"`, `sufficiency: "unknown"` with explicit
annotation and SHALL preserve the original artifact verbatim (no data loss).

#### Scenario: Legacy row migrated with explicit annotation

- **WHEN** the ledger migrates a pre-existing `outputs` row containing a bare
  artifact JSON
- **THEN** the row reads as a StageOutcome with `execution: "executed"`,
  `sufficiency: "unknown"`, and the original artifact recoverable verbatim
  from the outcome's legacy field

#### Scenario: Canvas projection reads the structured outcome

- **WHEN** the canvas projects a stage whose outputs are a StageOutcome
- **THEN** findings text, sources and (for parked stages) unresolved claims
  are displayed from the structured outcome

#### Scenario: Corrupt outputs fail closed to unknown

- **WHEN** an outputs value cannot be parsed as either format
- **THEN** the reader reports `execution: "executed"`, `sufficiency:
  "unknown"` rather than crashing or inventing a verdict

### Requirement: Sufficiency gates stage completion

`completeStage` SHALL run only when the sufficiency gate passes
(`sufficiency: "sufficient"`). All-irrelevant sources, empty results,
conflicting sources, and unavailable synthesis SHALL NOT complete a stage:
a failed synthesis is not a completed stage, and irrelevant or empty results
do not satisfy the research question or silently mark it solved.

#### Scenario: Irrelevant sources never complete

- **WHEN** every retrieved source is judged irrelevant to the stage claim
- **THEN** the stage does not complete; it records `sufficiency:
  "insufficient"` with an explicit unresolved claim stating the evidence gap

#### Scenario: Empty results never complete

- **WHEN** retrieval returns zero sources
- **THEN** the stage does not complete and records the empty-result gap as an
  unresolved claim

#### Scenario: Conflicting sources never silently complete

- **WHEN** synthesis reports conflicting evidence
- **THEN** the stage does not complete and records the conflict in
  unresolved claims

#### Scenario: Sufficient evidence completes

- **WHEN** at least one relevant source exists and synthesis is available and
  does not report a conflict
- **THEN** the stage completes with `sufficiency: "sufficient"`

### Requirement: Insufficient stages re-query with a stated information gain

An insufficient stage SHALL trigger exactly one re-query whose stated
information gain is derived from the recorded unresolved claims; if the
re-query is still insufficient, the stage SHALL park with explicit
unresolved claims visible in the persisted outcome. The re-query machinery
SHALL reuse the existing failStage retry/park state machine (bounded,
persistent across restarts).

#### Scenario: Refinement states its gain

- **WHEN** a stage is judged insufficient for the first time
- **THEN** the stage re-dispatches with the unresolved claims as the stated
  information gain, and the broadcast names that gain

#### Scenario: Refinement exhausted parks with unresolved claims

- **WHEN** the refinement round is also judged insufficient
- **THEN** the stage parks, and its persisted outcome carries
  `sufficiency: "insufficient"` and the unresolved claims (visible after
  restart)

### Requirement: No-progress loops stop mechanically

Repeated queries without stated gain and repeated near-identical findings
SHALL stop the loop mechanically: a query already searched in the same task
SHALL park its stage without paying for a second identical search, and two
consecutive near-duplicate finding sets SHALL set a task-level no-progress
flag that prevents graph growth (the arbiter no longer grows the graph; the
graph closes honestly on the current state).

#### Scenario: Duplicate query parks without a second search

- **WHEN** a stage's retrieval query is byte-equivalent (after
  normalization) to a query already executed in the same task
- **THEN** the stage records the no-progress stop reason, does not call the
  search provider again, and parks

#### Scenario: Repeated findings stop graph growth

- **WHEN** consecutive stage completions in a task produce near-duplicate
  findings (bigram novelty at or below the no-progress threshold)
- **THEN** the task-level no-progress flag is set, the arbiter wave refuses
  to grow new nodes, and the graph closes with a broadcast naming the
  no-progress stop

### Requirement: Summary reflects root question and full branch coverage

The summary node's title SHALL be derived from the task's root question (not
the first branch text), the arbiter prompt SHALL receive the root question
as the overall research question, and the summary outcome SHALL record
per-branch coverage (`answered`/`gap`) over all confirmed mindmap branches.

#### Scenario: Summary title uses the root question

- **WHEN** all non-summary nodes complete and the graph closes
- **THEN** the registered summary node is titled `汇总｜<root question>`
  even when the first branch is not the root question

#### Scenario: Summary coverage enumerates branches

- **WHEN** the summary stage completes
- **THEN** its outcome records a coverage entry for every confirmed branch
  with answered or gap status derived from the branch findings

### Requirement: Gain damping baselines are isolated per task

The damping update's comparison baseline SHALL be tracked per task: an
interleaved task's gain update SHALL NOT change another task's damping ratio
or its prior selection.

#### Scenario: Interleaved tasks do not cross-contaminate damping

- **WHEN** two tasks run interleaved and task B's stage completes with a
  high-gain posterior between task A's completions
- **THEN** task A's damping evolves exactly as it would have if task A ran
  alone

### Requirement: Relevance verdicts are explainable and degrade mechanically

Per-source relevance verdicts SHALL carry a stated basis. The deterministic
heuristic scorer SHALL run always (pure function, no paid call); structured
model verdicts from the existing synthesis call MAY override per-source
verdicts when present. When the synthesis model is unavailable, verdicts
SHALL come from the heuristic alone and the gate SHALL remain fully
mechanical.

#### Scenario: Heuristic runs without the model

- **WHEN** the synthesis model is unavailable and sources are retrieved
- **THEN** every source still receives a deterministic verdict with basis,
  and an all-irrelevant result set still fails the sufficiency gate

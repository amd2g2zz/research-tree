## ADDED Requirements

### Requirement: phase transitions have owned writers
Every run phase change is written by the component that owns the transition, through the gated tree-state graph, so the #492 transition gate executes on production paths.

#### Scenario: full-run phase sequence is persisted and queryable
- **WHEN** a run moves handoff-confirmed, slots-closed, and readiness-passed with a tree present
- **THEN** the store records exactly `research`, `validation`, `delivery` in order and the tree payload phase is queryable and matches

#### Scenario: handoff confirm writes the compiled birth phase
- **WHEN** the alignment handoff is confirmed and compiled into a research tree
- **THEN** the tree payload carries `phase=compiled` explicitly and the store records the transition

#### Scenario: illegal transitions are rejected by the pre-existing gate
- **WHEN** a writer (or any caller) asks for a phase outside the gated graph, e.g. `research -> delivery`
- **THEN** the tree-state service raises and nothing is persisted

#### Scenario: reopen re-entry writes alignment
- **WHEN** the reopen-alignment re-entry fires on a researching run
- **THEN** the tree phase becomes `alignment` through the legal reopen edge; a same-phase reopen is a no-op

### Requirement: the hook reads the authoritative phase store
Production phase resolution prefers the engine-written store over env and manifest guesses; the store is digest-checked.

#### Scenario: hook resolves the authoritative phase in production
- **WHEN** a prompt is submitted with no env phase and no manifest phase, but the store holds `research`
- **THEN** the observation resolves `research` and the two-option re-entry verdict is recorded (chatty drift is refused)

#### Scenario: missing or tampered store degrades fail-open
- **WHEN** the store is absent, or its payload no longer matches the stored digest
- **THEN** resolution falls back to env and manifest; a tampered store can never inject a phase

#### Scenario: the re-entry gate activates only in research
- **WHEN** the resolved phase is `alignment`
- **THEN** prompts carry no re-entry verdict; in `research` every prompt resolves through the two-option protocol

### Requirement: alignment asks refuse under the research phase
While the run phase is `research`, new alignment asks are mechanically refused; reopening is only the reopen re-entry path.

#### Scenario: plan redirects without an ask
- **WHEN** `plan()` runs while the phase is `research`
- **THEN** it returns a `reopen_alignment` redirect naming the re-entry protocol, consumes no turn, and mutates no controller state

#### Scenario: record is refused under research
- **WHEN** `record()` runs while the phase is `research`
- **THEN** it raises naming the refusal; no outcome is recorded

### Requirement: grounding is append-only and cache-friendly
Storage and injection are separate: full state stays in the store; a transition is stated once; the only per-turn surface is a bounded tail snapshot.

#### Scenario: exactly one event statement per transition turn
- **WHEN** a phase transition happens and the hook subsequently observes prompts
- **THEN** the statement is announced exactly once and never rebroadcast on later turns

#### Scenario: the snapshot line is single-line and order-stable
- **WHEN** the tail snapshot is rendered from the store (or from no store)
- **THEN** it is one line with fixed slots in fixed key order (`phase`, `stance`, `viol`, `topics`, `digest`), placeholder defaults without a store, and the digest segment binds the line to the store

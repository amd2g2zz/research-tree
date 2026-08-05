# Product Contracts

These contracts describe the target product state. They are intentionally
independent of the retired schema-2 research state and establish the starting
point for a new implementation.

## Input Ledger Entry

```jsonc
{
  "id": "input-001",
  "kind": "brief|article|note|draft|repository|log|prior_output|feedback|context_bundle|other",
  "origin": {
    "type": "user|workspace|url|repository|generated",
    "locator": "relative/path or URL"
  },
  "revision": {
    "branch": "main",
    "commit": "optional commit",
    "sha256": "optional content hash",
    "observed_at": "2026-07-31T00:00:00Z"
  },
  "read_scope": "files, paths, pages, or sections the agent may inspect",
  "role": "baseline|constraint|signal|evidence|history",
  "member_input_ids": [],
  "grouping": "user_provided|agent_composed|none",
  "used_by_rounds": ["round-001"]
}
```

Repository entries are read-only by default. A baseline must record the
relevant paths, symbols, interfaces, behavior, dependencies, tests, deployment
configuration, and change surface. Secret files, binaries, symlinks that leave
the repository, and unrelated large directories are outside the default scope.

For `kind: context_bundle`, `member_input_ids` records the materials supplied
together. The bundle itself preserves the user's grouping; every member keeps
its own ledger entry and may appear in more than one bundle. A non-bundle input
uses an empty `member_input_ids` list and `grouping: none`.

## Context Bundle

```jsonc
{
  "id": "input-bundle-001",
  "kind": "context_bundle",
  "origin": {"type": "user", "locator": "conversation turn or uploaded folder"},
  "member_input_ids": ["input-brief", "input-article-a", "input-note", "input-repository"],
  "grouping": "user_provided",
  "role": "baseline"
}
```

A Context Bundle can be one sentence, many documents, or a repository plus
other materials. Membership describes delivery context, not authority or
agreement. The agent does not flatten conflicting entries into a single source.

## Alignment Graph and Handoff

Before autonomous research, persist a temporal heterogeneous multigraph in
`.research-tree-alignment/<run-id>/alignment.db`. Nodes represent typed human
or agent beliefs, intent hypotheses, constraints, evidence, disagreements,
strategy, and closure oracles. Directed edges have independent IDs so the same
nodes may retain multiple relations with different provenance, time, and
confidence.

SQLite `nodes` and `edges` tables are rebuildable materialized views. The
append-only `events` table stores every complete revision; `controller` stores
the current turn and handoff gate. WAL, foreign keys, and transactions are
enabled on every controller connection.

```jsonc
{
  "kind": "alignment-handoff",
  "alignment_revision": 12,
  "alignment_digest": "sha256 of displayed graph projection",
  "objective": "confirmed outcome",
  "strategy": "confirmed autonomous research strategy",
  "execution_context": {
    "intended_use": [],
    "scope_boundaries": [],
    "delivery": [],
    "authority": [],
    "success_oracles": [],
    "feasibility": [],
    "constraints": []
  },
  "decision_slots": {},
  "baseline_findings": []
}
```

The handoff compiler runs only after explicit confirmation of the displayed
digest. Open agent-researchable nodes become Decision Slots; their oracles
become validation rules. Anchored reconnaissance evidence becomes Finding Packs
loaded into Research Tree revision zero with no realized gain. Indirect graph
paths and their relation semantics remain attached to observations. Evidence
without an anchor or a path to a current slot blocks compilation unless marked
`alignment_only`; an active `supersedes` edge removes its target obligation.
Human statements remain intent evidence and are never silently converted into
technical facts.

Closing every Decision Slot produces `delivery_pending`, not `complete`. The
runtime's `tree-deliver` command verifies both report files, records their
absolute path, UTF-8/no-BOM status, minimum depth, and digest, and only then
permits the terminal state.

## Repository Baseline

```jsonc
{
  "repository_root": "canonical local path or checked-out root",
  "read_scope": ["."],
  "revision": {
    "branch": "main or null",
    "commit": "commit or null",
    "dirty": false,
    "sha256": "safe-scan fingerprint or null",
    "observed_at": "2026-07-31T00:00:00Z"
  },
  "anchors": [{"path": "src/example.py", "symbol": "main or null"}],
  "facts": [{
    "category": "path|source|symbol|entry_point|behavior|interface|dependency|test|deployment|change_surface",
    "anchor": {"path": "src/example.py", "symbol": "optional"},
    "observation": "bounded, observed repository fact"
  }],
  "unreadable": [{"path": ".env", "reason": "secret"}]
}
```

A repository baseline is attached to its repository Input Ledger entry. Its
anchors must be repository-relative and resolvable against the recorded root
and revision. `unreadable` records boundary decisions without retaining file
content. The baseline is a read-only observation, not an architecture or intent
interpretation.

## Intent Model

```jsonc
{
  "id": "intent-002",
  "round_id": "round-002",
  "revision": 1,
  "context_bundle_ids": ["input-bundle-001"],
  "input_ids": ["input-brief", "input-article-a", "input-note", "input-repository"],
  "signals": [{
    "input_id": "input-note",
    "observation": "what the material literally says or demonstrates",
    "kind": "stated_goal|constraint|preference|repository_fact|context|other",
    "authority_boundary": "what the signal can and cannot establish"
  }],
  "hypotheses": [{
    "id": "intent-hypothesis-01",
    "interpretation": "the requester is trying to enable ...",
    "status": "leading|viable|rejected|needs_user_input",
    "signal_refs": ["input-note"],
    "confidence": "low|medium|high",
    "decision_consequence": "which research or blueprint choices would change",
    "validation": "alignment_research|repository_inspection|experiment|user_question|none"
  }],
  "desired_outcomes": [],
  "success_signals": [],
  "decision_drivers": [{"dimension": "technical|user|delivery|commercial|risk|other", "statement": "...", "signal_refs": []}],
  "hard_constraints": [],
  "non_goals": [],
  "unresolved_interpretations": []
}
```

The Intent Model is the agent's revisable understanding of what the requester
is trying to achieve. It does not turn an inference into a user requirement.
It keeps multiple viable interpretations when their consequence is material and
only asks the requester when available inputs, repository facts, and bounded
alignment research cannot responsibly distinguish a non-recoverable choice.

## Working Brief

```jsonc
{
  "id": "brief-002",
  "round_id": "round-002",
  "parent_round_id": "round-001",
  "triggers": [{
    "kind": "initial_request|feedback|new_material|new_repository",
    "text": "one event that starts or reshapes this round",
    "input_ids": ["input-001", "input-007"]
  }],
  "context_bundle_ids": ["input-bundle-001"],
  "selected_input_ids": ["input-brief", "input-article-a", "input-note", "input-repository"],
  "intent_model_id": "intent-002",
  "intent_hypothesis_ids": ["intent-hypothesis-01"],
  "input_roles": {
    "input-brief": "primary",
    "input-article-a": "context",
    "input-note": "constraint",
    "input-repository": "baseline"
  },
  "working_interpretation": "the strategy-ready interpretation selected from the Intent Model",
  "material_conflicts": [{"input_ids": ["input-article-a", "input-note"], "status": "open|scoped|resolved", "note": "..."}],
  "technical_outcome": "the capability or design decision to enable",
  "non_goals": [],
  "retained_hard_constraints": [],
  "assumptions": [],
  "prior_material_disposition": {
    "finding-001": "reuse|revalidate|downgrade|ignore|overturn"
  },
  "delivery_targets": {
    "technical_research_package": true,
    "human_research_report": true,
    "openspec": false
  }
}
```

This is an internal Working Brief, not a single user material or the source of
truth for intent. It snapshots the Intent Model interpretation selected for the
strategy. A strategy can select individual bundle members, a whole bundle, or
independent inputs. It must preserve the role, authority boundary, unresolved
conflict, and viable alternative interpretation of every selected item.
Unmentioned or previously accepted material is not automatically retained; the
new strategy decides its disposition.

## Research Strategy

```jsonc
{
  "id": "strategy-002",
  "brief_id": "brief-002",
  "intent_model_id": "intent-002",
  "technical_outcome": "...",
  "context_bundle_ids": ["input-bundle-001"],
  "baseline_input_ids": ["input-001", "input-002"],
  "input_disposition": {
    "input-001": "primary|constraint|context|counterexample|out_of_scope",
    "input-002": "primary|constraint|context|counterexample|out_of_scope"
  },
  "blueprint_target_id": "blueprint-target-002",
  "tracks": [{
    "id": "architecture",
    "question": "Which architecture can meet the outcome in this repository?",
    "intent_hypothesis_ids": ["intent-hypothesis-01"],
    "decision_slot_ids": ["decision-slot-architecture"],
    "decision_value": "Changes the main integration boundary",
    "priority": 1,
    "methods": ["repository_inspection", "primary_docs", "prototype"],
    "evidence_standard": "...",
    "depth": "bounded|deep",
    "exit_criteria": ["..."],
    "status": "planned|active|complete|deferred"
  }],
  "budget": {
    "time": "bounded default or explicit value",
    "source_limit": "bounded default or explicit value",
    "prototype_limit": "bounded default or explicit value",
    "monetary": "unset unless explicitly supplied by the requester"
  },
  "autonomy": {
    "ask_user": "only non-recoverable unresolved decisions",
    "assumption_policy": "record and validate later",
    "continuation_policy": "persist checkpoint and resume; do not treat operational guardrails as infeasibility"
  },
  "strategy_changes": [],
  "delivery_targets": {
    "technical_research_package": true,
    "human_research_report": true,
    "openspec": false
  }
}
```

Tracks organize work; they are not completion units. A completed strategy can
still be incomplete when a critical Decision Slot is open. The strategy must
also state which Intent Model hypotheses it carries, tests, or intentionally
leaves viable, so later technical choices do not lose their reason for existing.

## Blueprint Target and Decision Slot

```jsonc
{
  "id": "blueprint-target-002",
  "brief_id": "brief-002",
  "intent_model_id": "intent-002",
  "revision": 1,
  "slots": [{
    "id": "decision-slot-architecture",
    "kind": "architecture|interface|state|security|migration|validation|operations|other",
    "question": "Which technical choice must be made?",
    "intent_hypothesis_ids": ["intent-hypothesis-01"],
    "priority": "P0|P1|P2",
    "impact": "low|medium|high",
    "uncertainty": "low|medium|high",
    "irreversibility": "low|medium|high",
    "constraints": ["explicit constraint or repository fact id"],
    "alternatives": ["candidate-a", "candidate-b"],
    "repository_touchpoints": [{"path": "src/example.ts", "symbol": "optional"}],
    "depends_on": [],
    "evidence_standard": "primary docs plus repository check",
    "closure_rule": "selected, conditional with validation, or deferred with fallback",
    "status": "open|researching|selected|conditional|deferred|blocked"
  }]
}
```

A Blueprint Target is revisable within a round. Each revision records why a
slot was added, removed, split, merged, or reprioritized. It must not be used as
a mandatory pre-research questionnaire.

## Work Item and Finding Pack

```jsonc
{
  "id": "work-014",
  "round_id": "round-002",
  "decision_slot_id": "decision-slot-architecture",
  "intent_hypothesis_ids": ["intent-hypothesis-01"],
  "kind": "external_research|repository_analysis|prototype|evaluation",
  "scope": "one bounded question and its exclusions",
  "depends_on": ["work-003"],
  "methods": ["primary_docs", "repository_inspection"],
  "budget": {"tool_calls": 12, "time": "bounded"},
  "completion_rule": "return a Finding Pack or explain why evidence is unavailable",
  "status": "planned|ready|running|complete|cancelled|deferred"
}
```

```jsonc
{
  "id": "finding-014",
  "work_item_id": "work-014",
  "attempt_id": "attempt-runtime-id",
  "phase": "landscape|deep_dive|adversarial|validation",
  "observations": [{
    "claim": "atomic observed fact",
    "anchor": {"kind": "source|repository|input|experiment", "ref": "URL or path:symbol"},
    "applicability": "conditions and version scope",
    "confidence": "low|medium|high",
    "limitation": "what this does not establish"
  }],
  "option_effects": [{"option": "candidate-a", "effect": "supports|contradicts|limits"}],
  "implementation_implications": [],
  "remaining_uncertainties": [],
  "research_node_id": "node:decision-slot-architecture:...",
  "research_continuations": [{
    "kind": "deep_dive|adversarial|validation|method_switch",
    "question": "one successor question triggered by this evidence",
    "trigger": "why the current evidence created this action",
    "evidence_needed": "the missing evidence class",
    "oracle": "observable condition that closes the child",
    "estimated_cost": 1
  }],
  "validation_result": {
    "status": "passed|failed|inconclusive",
    "oracle": "the oracle that was evaluated",
    "evidence_ref": "source or executed artifact reference"
  }
}
```

`attempt_id` and `phase` are execution-provenance fields required by the
bundled native host adapter. The coordinator maps the verified pack into the
immutable round artifact rather than treating schema validation as evidence
review. A retry receives a new `attempt_id`; a pack from an older attempt must
not close the current work item.

Workers return Finding Packs, not standalone report chapters. A source list
without atomic observations and decision effects is not a Finding Pack.
`research_continuations` is the only worker-controlled growth proposal. The
coordinator deduplicates, scores, and may reject it; workers do not mutate the
active tree or assign their own information-gain score.

### Host event binding

Host events that describe an attempt (`attempt_started`, `finding_submitted`,
`review_completed`, `provider_failed`, `attempt_unknown`, `retry_requested`,
or `worker_finished`) must carry an `attempt_id` already issued by the
coordinator. Ingestion checks both the expected run revision and the
`action_attempts` row before appending the event. A missing or unknown attempt
is rejected without mutating the ledger. An attempt whose lease is already
`unknown` may report `attempt_unknown`, but it cannot later submit a success
event. Duplicate event IDs remain idempotent only when their payload digest is
unchanged. Host-visible status never closes the work item or run by itself.

The coordinator also validates the minimum payload for each event before
persisting it: `finding_submitted` requires the Finding Pack and output
digests, evidence refs, and submission status; `worker_finished` requires a
terminal status and artifact refs; `provider_failed` requires provider/model,
retry category, opaque code, and safe gateway-log ref; and
`reconciliation_detected` requires host/canonical observations, conflict
class, and next action. Other event types use their corresponding field list
in the HostEvent protocol specification.

Accepted attempt events may project a lease to `running`, `submitted`,
`verified`, `retryable`, `unknown`, or `rejected` according to the event and
its payload. This projection is an observation for reconciliation; it never
issues a closure token or changes the run lifecycle to `completed`.
When an attempt is `retryable` or `unknown`, `ResearchRunCoordinator.retry_attempt`
creates a new attempt identity and lease, preserves the predecessor as
evidence, and records the method/provider dispatch digest used by the retry.

## Persistent recursive research state

Every accepted batch appends a `research-tree-state` artifact. Revision zero
loads existing Finding Packs as the evidence baseline and records no realized
gain. Later revisions reference the previous tree state and exactly the new
Finding Packs they consume. The state includes active and terminal nodes,
Decision Slot closure status, evidence fingerprints, measured deltas,
bounded residual risk, observed branch complexity, validation outcomes,
penalties, and the stop reason. Failed validation raises the slot's bounded
residual and grows an independent-method retry; passed validation removes that
closure deficit. Recovery loads the latest revision and replays
persisted Finding Packs absent from `consumed_finding_ids`. It also stores the
exact execution context and a two-entry `deliverables` manifest. Once all
Decision Slots close, the state becomes `delivery_pending` until `tree-deliver`
verifies both report artifacts; only then may it become `complete`.

## Decision Ledger Entry

```jsonc
{
  "id": "decision-009",
  "round_id": "round-002",
  "decision_slot_id": "decision-slot-architecture",
  "status": "selected|conditional|deferred|blocked",
  "selected_option": "candidate-a",
  "alternatives": [{"option": "candidate-b", "disposition": "rejected|deferred", "reason": "..."}],
  "anchors": ["finding-014", "repo:path:symbol"],
  "design_consequence": "component, interface, or state change",
  "repository_touchpoints": ["src/example.ts:Example"],
  "validation": {"kind": "test|spike|metric|review", "oracle": "observable pass condition"},
  "assumptions": [],
  "fallback": "safe behavior when the condition fails",
  "reversal_condition": "new evidence or outcome that changes this choice"
}
```

The Technical Research Package is compiled from the Decision Ledger. Each P0
entry needs a traceable path from anchor to design consequence, change task, and
acceptance oracle.

## Readiness Record

```jsonc
{
  "id": "readiness-002",
  "round_id": "round-002",
  "blueprint_target_revision": 1,
  "gates": {
    "intent_alignment": "pass|fail|deferred",
    "decision_closure": "pass|fail",
    "traceability": "pass|fail",
    "repository_fit": "pass|fail|not_applicable",
    "implementation_readiness": "pass|fail|deferred",
    "operational_quality": "pass|fail|deferred"
  },
  "risk_tier": "default|medium|high",
  "findings": [],
  "next_work_item_ids": []
}
```

A failed readiness gate becomes a targeted same-round work item unless it
changes the user's target or success definition. `intent_alignment` checks that
the leading interpretation and material alternatives remain visible in the
blueprint; it is not a claim that the agent has proven the user's private
intent. Only target-changing feedback starts a new Working Brief.

## Research Round

```jsonc
{
  "id": "round-002",
  "brief_id": "brief-002",
  "intent_model_id": "intent-002",
  "strategy_id": "strategy-002",
  "parent_round_id": "round-001",
  "status": "planning|researching|ready|superseded|complete",
  "artifact_refs": {
    "intent_model": "research/round-002/intent-model.json",
    "technical_research_package": "research/round-002/agent-package.md",
    "human_research_report": "research/round-002/human-research-report.md",
    "decision_ledger": "research/round-002/decision-ledger.json",
    "readiness_record": "research/round-002/readiness.json",
    "openspec": null
  },
  "superseded_by_round_id": null
}
```

`superseded` means the current strategy should not receive more normal work.
It does not delete evidence or artifacts; they remain candidate context for the
next Brief.

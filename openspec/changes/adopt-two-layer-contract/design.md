# Design: adopt-two-layer-contract

## Context

Issue #501 records the 2026-09-03 architecture ruling (full rationale and
canonical loop in ADR-008): the engine never enumerates *what* the agent may
say — it gates on *what structural traces the agent must leave*; the prompt
layer carries all open-ended strategy as craft guidance, and anything
load-bearing gets an engine-side structural gate. This change ratifies the
ruling as ADR-008, delivers the mechanical seam plus the plan-mandated audit
script and PR template, and deliberately does NOT rewire the alignment
controller (that is #489/#490's file ownership).

## Goals / Non-Goals

**Goals:**

- ADR-008: two-layer contract, design test, canonical contract-emission loop,
  rejected design.
- `src/research_tree/turn_contract.py`: contract-terms schema (`target_gap` /
  `required_traces` / `cost_cap` / `taboos`), frozen append-only trace-type
  registry (six initial types, duplicate registration rejected), and
  `verify_traces()` that fails naming the exact missing term — presence+schema
  only, never content quality.
- `scripts/check_impact_scope.py`: deterministic, offline reconciliation of
  changed files against a declared impact scope.
- `.github/PULL_REQUEST_TEMPLATE.md` checklist; `.gitignore` gains `plan.md`.

**Non-Goals:**

- Wiring the seam into `alignment_graph.py`, `decision_frame.py`, or
  `lifecycle_hook.py` (#489/#490 own those files; this PR must not touch them).
- Turn-record persistence (#497), turn-shape metrics (#493),
  `proportionality_assessment` (#498), transformation traces (#499) — later
  waves append to the registry and consume the seam.
- Any prompt-layer rewrite (#500) or packages regeneration (no `skill-src`
  change here, so parity is untouched).
- Promoting pydantic to a runtime dependency (ADR-007 leaves it in the test
  group; runtime stays stdlib-only per ADR-001).

## impact_scope

Entirely additive. Index rebuilt via
`node /Users/mikenike/workprojects/research-tree/.gitnexus/run.cjs analyze .`
at branch tip `64224ee`, and again at the final HEAD before the
detect-changes reconciliation recorded in `evidence/`.

| Symbol / file | Status | Risk | Upstream callers |
|---|---|---|---|
| `src/research_tree/turn_contract.py` (all new symbols) | added | LOW | none — deliberate seam, uncalled until #489/#490 |
| `scripts/check_impact_scope.py` (`main`, `audit_impact_scope`, loaders) | added | LOW | none — standalone gate helper |
| `tests/test_turn_contract.py`, `tests/test_check_impact_scope.py` | added | LOW | pytest collection only |
| ADR-008, PR template, openspec change folder, evidence sidecar, `.gitignore`, documentation-authority registry entry | added | LOW | none (docs/config) |

No existing symbol is modified, renamed, or removed, so upstream blast radius
is empty by construction. Expected risk level: LOW (the plan's HIGH-risk
item, controller rewiring, belongs to #489).

## Decisions

### Contract terms are one strict schema, serialized as one mapping

`ContractTerms` carries exactly `schema_version` (1), `target_gap`
(alignment-graph node id, matching the `alignment_graph.IDENTIFIER_RE` shape,
kept local so the seam does not import the sqlite-backed graph module),
`required_traces` (finite, deduplicated, every name registered), `cost_cap`
(below), and `taboos` (unique node ids already answered or whose asks are
spent — `MAX_ASKS_PER_NODE` migrates here at #489 wiring time). Serialization
follows the repo's whitelist pattern (`set(value) != {...}`, errors naming
the offending field); missing AND unknown fields are both rejected.

### cost_cap discriminates response classes, not byte counts

The cap models bytes-to-decide: a `discrimination` response (point at an
option, confirm/deny) is capped at exactly one sentence (一句指认); a
`generation` response may carry free text (optional explicit sentence budget,
`None` = unbounded here). The two-value class is contract space the engine
verifies — not behavior space; the user's actual text stays unenumerated.

### The trace-type registry is an immutable value, extended by rebinding

`TraceTypeRegistry` is frozen; `register()` returns a NEW registry;
registering an existing name raises `DuplicateTraceTypeError`; there is no
unregister/redefine path — append-only semantics. `DEFAULT_TRACE_REGISTRY` is
seeded with exactly the six initial types from the issue and never mutated at
import time. S4 waves (#493/#498/#499) append entries with zero merge-conflict
surface and cannot silently weaken a schema earlier waves gate on. Each type
declares its payload's required fields for the presence+schema checks.

### verify_traces fails closed, naming the term

`verify_traces(terms, traces)`: every required trace type must be present
among the recorded traces (missing → `MissingTraceError` naming the exact
term), every recorded type must be registered, every payload must carry the
type's declared required fields. Content quality is never inspected — the
engine's silence about "how good" is the contract working. Success returns
the satisfied required-trace tuple for the turn-record (#497).

### The seam is stdlib-only and unwired

Runtime dependencies stay `[]` (ADR-001). ADR-007's pydantic boundary applies
when pydantic is promoted to runtime deps and `schemas.py` exists — the
whitelist-validation style here is the codebase's existing pattern (~420
sites); centralizing is deferred until a second consumer exists (#489). No
production module imports `turn_contract` yet; being uncalled is what makes
it a seam.

### check_impact_scope consumes machine-readable output when available

Observed on the installed CLI (`detect-changes --help`): scopes
`unstaged|staged|all|compare`, `--base-ref`, `--repo`, `--limit` — no JSON
flag; output is human-readable prose, and parsing it would be fragile
theater. The script therefore accepts a saved detect-changes JSON report
(future versions / exports) or falls back to `git diff --name-only
<base>...HEAD` against the declared file scope — a documented FILE-LEVEL
audit, deterministic, offline, MCP-free. The `impact-scope-v1` sidecar
declares `files` (exact repo-relative paths) and optional `symbols`, lives in
the change's `evidence/` directory (outside the delivery-policy ignore globs,
so it is commitable and wave-reviewable), and the PR template keeps the
human-checked detect_changes checklist in the loop.

## Rejected Designs

- **Behavior enumeration in engine vocabulary** (the ruling's rejected
  design, recorded so future issues cannot reintroduce it): `POLICY_ACTIONS`-
  style menus (e.g. a 13-action table of guidance moves) or fixed selection
  ladders over them — they cannot cover the generation space (the #501 root
  cause). Guidance-form illustrations belong in prompt-layer craft docs.
  Design test: an enum entry for something the model should say violates the
  contract; a trace type the engine can verify conforms.
- **Pydantic schemas in a new `schemas.py` now**: pydantic is still
  test-group only (ADR-007); revisit at #489 when a second consumer exists.
- **Wiring contract emission into `ClarificationPolicy.evaluate` /
  alignment_graph in this PR**: owned by #489/#490/#496; would collide with
  parallel worktrees and re-create the HIGH-risk blast radius this wave
  isolates.
- **Mutable registry with `unregister`/`redefine`**: redefinition would let a
  later wave silently weaken a schema earlier waves already gate on.
- **Content-quality checks in `verify_traces`**: the quote-ratio-police
  pattern the ruling rejects; the engine verifies that a structural trace
  exists and is well-formed, never what it says.
- **Symbol-level audit by parsing the CLI's prose output**: fragile across
  GitNexus versions; supported only as JSON consumption when a report exists.

## Risks / Trade-offs

- [Seam drift: #489 needs fields this PR did not anticipate] ->
  schema_version from day one; additive optional keys follow the tree_state
  precedent; the six trace types come verbatim from the issue.
- [File-level fallback may miss a changed symbol inside a declared file] ->
  documented limitation; PR template keeps the human checklist in the loop.
- [Six initial types under-specify payloads] -> required_fields start minimal
  (one structural key each); refined shapes register NEW types, never
  redefine existing ones.

## Migration Plan

No data migration. Nothing persists yet (turn-record persistence is #497);
the module is importable and tested, the audit script is runnable
standalone, and the PR template applies to the next PR opened in the repo.

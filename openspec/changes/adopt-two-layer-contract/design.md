# Design: adopt-two-layer-contract

## Context

Issue #501 records the 2026-09-03 architecture ruling: engine-side behavior
enumeration cannot cover open-ended alignment behaviors (通过词表肯定是无法覆
盖的，很多需要通过 prompt 来解). The prompt layer already carries ~2000 lines
of craft guidance (teaching cycles, counterarguments, short-round discipline)
yet none of it is engine-enforced; engine vocabulary attempts
(`alignment_graph.py` 19 node types / `POLICY_ACTIONS` in `decision_frame.py`,
4 actions) cannot express the behaviors the prose promises. The ruling splits
the system into two layers with a hard division principle: the engine never
enumerates *what* the agent may say — it gates on *what structural traces the
agent must leave*; the prompt layer carries all open-ended strategy as craft
guidance, and anything load-bearing gets an engine-side structural gate.

This change ratifies the ruling as ADR-008 and delivers the mechanical seam
(`turn_contract.py`) plus the plan-mandated impact-scope audit script and PR
template. It deliberately does NOT rewire the alignment controller: that is
#489/#490's file ownership.

## Goals / Non-Goals

**Goals:**

- ADR-008 stating the two-layer contract, the design test, the canonical
  contract-emission loop, and the rejected design.
- `src/research_tree/turn_contract.py`: contract-terms schema
  (`target_gap` / `required_traces` / `cost_cap` / `taboos`), frozen
  append-only trace-type registry (six initial types, duplicate registration
  rejected), `verify_traces()` that fails naming the exact missing term —
  presence+schema only, never content quality.
- `scripts/check_impact_scope.py`: deterministic, offline reconciliation of
  changed symbols/files against a declared impact scope.
- `.github/PULL_REQUEST_TEMPLATE.md` with the mandatory checklist.
- `.gitignore` gains `plan.md` under "# Local configuration".

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
at branch tip `64224ee` (issue #501 worktree `rt-wt-501`).

| Symbol / file | Status | Risk | Upstream callers |
|---|---|---|---|
| `src/research_tree/turn_contract.py` (all new symbols: `CostCap`, `Taboos`, `ContractTerms`, `TraceType`, `TraceTypeRegistry`, `verify_traces`, errors) | added | LOW | none — deliberate seam, uncalled until #489/#490 |
| `scripts/check_impact_scope.py` (`main`, `audit_impact_scope`, loaders) | added | LOW | none — standalone gate helper |
| `tests/test_turn_contract.py`, `tests/test_check_impact_scope.py` | added | LOW | pytest collection only |
| `docs/adr/ADR-008-two-layer-contract.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `openspec/changes/adopt-two-layer-contract/**`, `.gitignore` | added | LOW | none (docs/config) |

No existing symbol is modified, renamed, or removed, so upstream blast radius
is empty by construction; GitNexus `impact` on the new symbols returns no
callers and `detect-changes --scope compare --base-ref dev` is reconciled
against this table with `check_impact_scope.py` and recorded in `evidence/`
before push. Expected risk level: LOW (the plan's HIGH-risk item, controller
rewiring, belongs to #489).

## Decisions

### Contract terms are one strict schema, serialized as one mapping

`ContractTerms` carries exactly `schema_version` (1), `target_gap`
(alignment-graph node id, matching the `alignment_graph.IDENTIFIER_RE`
shape), `required_traces` (finite, deduplicated set of registered trace-type
names), `cost_cap` (see below), and `taboos` (unique node ids already answered
or whose asks are spent — `MAX_ASKS_PER_NODE` migrates here at #489 wiring
time, not now). Serialization follows the repo's whitelist pattern
(`set(value) != {...}` with errors naming the offending field, per ADR-007's
error-message requirement and the `decision_frame.py`/`tree_state.py`
precedents). Missing AND unknown fields are both rejected.

### cost_cap discriminates response classes, not byte counts

The cap models bytes-to-decide, not bytes-to-read: a `discrimination` class
user response (point at an option, confirm/deny) is capped at exactly one
sentence (一句指认); a `generation` class response may carry free text
(bounded only by an optional explicit sentence budget, `None` = unbounded by
this seam). The class is an enumerated field because it is a *contract term*
the engine verifies — the two-value enumeration is contract space, not
behavior space; the text the user actually writes stays unenumerated.

### The trace-type registry is an immutable value, extended by rebinding

`TraceTypeRegistry` is frozen; `register()` returns a NEW registry. The
module-level `DEFAULT_TRACE_REGISTRY` is seeded with exactly the six initial
types (option-set, concept-card, guess-statement, counterargument,
possibility-survey, evidence-delta) and is never mutated at import time.
Registering a name that already exists raises `DuplicateTraceTypeError`, and
there is no unregister/redefine path — append-only semantics. S4 waves
(#493/#498/#499) therefore append entries with zero merge conflict surface and
cannot silently redefine an existing trace type. Each trace type declares its
payload's required fields so `verify_traces` can do presence+schema checks.

### verify_traces fails closed, naming the term

`verify_traces(terms, traces)` checks, per required trace type: at least one
recorded trace of that type exists (missing → `MissingTraceError` whose
message names the exact required term, e.g. `possibility-survey`), every
recorded trace's type is registered (unknown → named schema error), and each
required type's payload carries all declared required fields. It never
inspects content quality, wording, length beyond declared structural fields,
or "how good" the artifact is — that is the prompt layer's job and no engine
checklist may grow there. Success returns the satisfied required-trace tuple
for persistence into the turn-record (#497).

### The seam is stdlib-only and unwired

Runtime dependencies stay `[]` (ADR-001); ADR-007's pydantic boundary applies
when pydantic is promoted to runtime deps and `src/research_tree/schemas.py`
exists — the whitelist-validation style here is the same pattern that codebase
already uses (~420 sites) and centralizing into `schemas.py` is deferred until
a second consumer exists (#489). No production module imports
`turn_contract` yet; being uncalled is what makes it a seam.

### check_impact_scope consumes machine-readable GitNexus output when available

Grounded in `node .gitnexus/run.cjs detect-changes --help` (options: `--scope
unstaged|staged|all|compare`, `--base-ref`, `--repo`, `--limit`). The script
accepts a saved detect-changes JSON report plus an `impact_scope` sidecar and
fails when a changed symbol's file falls outside the declared scope; when a
detect-changes report is unavailable (the CLI prints human-readable output
and the JSON shape is version-dependent — see script docstring for the exact
limitation observed on the installed version), it falls back to
`git diff --name-only <base>...HEAD` cross-referenced against the declared
file scope. Both modes are deterministic, offline, and MCP-free; the fallback
is explicitly file-level (documented limitation, not a symbol-level audit).

### impact_scope sidecar lives in the change's evidence/ directory

Per the delivery policy's `ephemeral_verification_paths`, JSON reports under
`openspec/changes/<id>/evidence/` are not matched by the ignore globs (which
cover `-output.txt`, `-output.log`, `-receipt.json`, `verification-*.md`, and
specific named JSONs), so a `detect-changes-report.json` / `impact-scope.json`
pair there is commitable and wave-reviewable. The sidecar schema
(`impact-scope-v1`) declares `files` (exact repo-relative paths) and optional
`symbols` (name + file + status), and is validated with named errors.

## Rejected Designs

- **Behavior enumeration in engine vocabulary (the ruling's rejected design,
  recorded so future issues cannot reintroduce it)**: expanding
  `POLICY_ACTIONS`-style menus (e.g. a 13-action table of echo-guess /
  example-anchor / teach-then-verify / constraint-menu /
  proportionality-challenge / consequence-warning moves) or fixed selection
  ladders over them. Rejected: the menus cannot cover the generation space
  (that is the #501 root cause); guidance-form illustrations belong in
  prompt-layer craft docs as teaching material for the composer and must never
  become engine enums or selection ladders. The design test: if it adds an
  enum entry for something the model should say, it violates the contract; if
  it adds a trace type the engine can verify, it conforms.
- **Pydantic schemas in a new `schemas.py` now**: rejected for this PR —
  pydantic is still test-group only (ADR-007 leaves promotion to an explicit
  maintainer decision) and `turn_contract.py` is runtime code; deferring also
  keeps this PR's file ownership to the seam itself. Revisit at #489 when a
  second consumer exists.
- **Wiring contract emission into `ClarificationPolicy.evaluate` /
  `alignment_graph` in this PR**: rejected — those files are owned by
  #489/#490/#496; touching them here would collide with three parallel
  worktrees and re-create the HIGH-risk blast radius this wave isolates.
- **Mutable module-level registry with `unregister`/`redefine`**: rejected —
  append-only is the contract; redefine would let a later wave silently
  weaken an existing trace's schema that earlier waves already gate on.
- **Content-quality checks in `verify_traces` (regex or classifier on trace
  payloads)**: rejected — that is the quote-ratio-police pattern the ruling
  rejects; the engine verifies that a structural trace exists and is
  well-formed, never what it says.
- **Symbol-level audit without GitNexus JSON**: rejected as the only mode —
  the script supports it only behind a documented CLI limitation; claiming
  symbol-level reconciliation from text parsing would be fragile theater.

## Risks / Trade-offs

- [Seam drift: #489 wires the contract and discovers the schema needs fields
  this PR did not anticipate] -> schema_version is present from day one;
  additive field growth via optional keys follows the tree_state optional-key
  precedent; the six initial trace types come verbatim from the issue so the
  S4 waves can register against them unchanged.
- [File-level fallback may miss a changed symbol inside a declared file] ->
  documented limitation; the primary mode consumes the GitNexus report, and
  the PR template keeps the human-checked detect_changes/impact_scope
  checklist in the loop.
- [Six initial types under-specify payloads] -> required_fields start minimal
  (each type declares the structural keys the issues name, e.g. option-set
  carries `options`); S4 waves widen their own types, never others'.

## Migration Plan

No data migration. Nothing persists yet (the turn-record persistence is
#497); the module is importable and tested, the audit script is runnable
standalone, and the PR template applies to the next PR opened in the repo.

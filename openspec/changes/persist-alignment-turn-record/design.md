# Design: persist-alignment-turn-record

## Context

Issue #497: the alignment-turn record ("Persist an alignment-turn record
(mirror, gap, evidence, delta, decision effect) after each meaningful
exchange", SKILL.md:222) is prose with no writer and no reader-gate. The
alignment SQLite graph persists only when the controller reference flow is
explicitly run; nothing binds the *agent's conversational* turns to a file.
After 3-4 turns (or compaction) the agent's model of the brief decays and it
starts self-asking/self-answering. User ruling: 对齐表现要在 research-tree
文件里面体现；不写文件就无法更新. ADR-008's canonical loop ends in "Persist
(per #497) the turn-record"; the seam module `turn_contract.py` (#504)
delivers the terms/traces schema this record must carry. This change is the
persistence layer + continuity gate + hook refresh; wiring contract emission
into the controller stays with #489/#490.

## Goals / Non-Goals

**Goals:**

- The alignment turn record is a first-class workspace file: append-one-JSON
  -line-per-turn under the run's existing `alignment/` directory.
- Fail-closed continuity gate: a missing, invalid, or stale record blocks the
  next alignment turn with a named reason (checkpoint-style discipline).
- Self-ask/self-answer guard: a turn introducing no persisted delta is a
  protocol violation and is rejected.
- Hook support: `UserPromptSubmit` / `PostToolUse` refresh and validate the
  record file (fail-open) so compaction or long sessions cannot silently
  orphan it; verdict surfaced on the hook result and record.
- Reuse the `turn_contract` seam schema (terms, response classes, trace
  registry, `verify_traces`) — never duplicate it.

**Non-Goals:**

- Wiring contract-term emission or the controller onto the record
  (`alignment_graph.py` untouched — owned by #496/#491; emission is #489).
- Response-class classification of prompts (#490 owns the five-signal model;
  the record only carries the classified response class it is given).
- Blocking the host session from the hook: the lifecycle hook stays fail-open
  by design; the continuity gate blocks at the record-protocol level (append
  and `check_continuity`), and the prompt layer honors the block.
- Hermes turn-record refresh: Hermes has no user-prompt or post-tool hook
  mechanism (N/A by design, per the existing hook template tests).

## impact_scope

Index rebuilt via `node .gitnexus/run.cjs analyze .` in the #497 worktree at
branch tip `50621df` (15,156 nodes / 31,018 edges) before any edit; impact
run upstream per modified symbol; detect-changes reconciliation stored in
`evidence/` before push.

| Symbol / file | Status | Risk | Upstream callers (from impact) |
|---|---|---|---|
| `lifecycle_hook.observe` | modified | **LOW** (2 impacted) | direct caller `main`; module `Research_tree`; flow: main |
| `lifecycle_hook._observe_prompt_signal` | modified | **LOW** (3 impacted) | `observe` (+ packaged mirrors); flow: main |
| `alignment_turn_record.*` (new module) | added | LOW (no upstream callers — new surface) | tests, hook refresh, prompt layer |
| `tests/test_alignment_turn_record.py`, `tests/test_lifecycle_hook_turn_record.py` | added | LOW | pytest collection |
| `skill-src/SKILL.template.md`, `skill-src/hermes-SKILL.template.md` | modified (persistence clause only) | LOW | `build_skill_packages.py` |
| `packages/**` | regenerated | LOW (generated) | parity gate |

No HIGH/CRITICAL blast radius: both modified hook symbols are LOW risk; the
new module has no upstream callers. The #503 re-entry protocol constants and
rules are untouched; its test suite is a regression gate.

## Decisions

### One JSONL file under the run's alignment directory

`project_workspace.RUN_DIRECTORIES` already provisions `alignment/` inside
every run root. The record file is
`<run_root>/alignment/turn-records.jsonl` — one strict-whitelist JSON object
per line, append-only (O_APPEND single-write), matching the issue's "state
file exists, grows per turn". A companion receipt
`<run_root>/alignment/turn-records.state.json` (atomic replace,
`_atomic_json` pattern) is written by the hook refresh: `{schema, state,
record_count, last_turn_index, validated_at}`. The receipt is evidence of
refresh only; the gate's authority is the record file itself.

### Record schema reuses the turn_contract seam

Fields: `schema` (1), `turn_index` (1-based exchange number), `mirror`,
`gap`, `delta` ({`summary` non-empty, `nodes` unique node-id-shaped
strings}), `user_move` (must be one of `turn_contract.RESPONSE_CLASSES` —
the seam's classified user-response vocabulary, feeding #490's model),
`contract_terms` (optional; round-trips through
`turn_contract.ContractTerms.from_dict`), `traces` (optional; each
`{type, payload}` validated against `turn_contract.DEFAULT_TRACE_REGISTRY`),
`recorded_at` (UTC ISO). When `contract_terms` is present, `traces` MUST
satisfy `turn_contract.verify_traces` (missing required trace fails naming
the exact term); traces without terms are validated structurally against
the registry. Validation is presence-and-schema only (ADR-008) — never
content quality.

### Fail-closed continuity gate with named reasons

`AlignmentTurnRecordStore.check_continuity(next_turn)`:
- file missing / empty and `next_turn > 1` → block `missing_turn_record`;
- any malformed record line or schema violation → block
  `invalid_turn_record`;
- `latest.turn_index < next_turn - 1` → block `stale_turn_record` (an
  exchange elapsed without a persisted record — the drift case);
- `latest.turn_index == next_turn - 1` → allow, returning the grounding
  (latest mirror/gap/delta) the move must be grounded in;
- `latest.turn_index >= next_turn` → allow as re-grounding (the record for
  this exchange is already persisted — the compaction/crash recovery path);
- `next_turn == 1` with an empty store → allow (opening turn).

`append()` enforces the same adjacency independently (`turn_index` must be
exactly `latest + 1`, else `missing_turn_record` / `duplicate_turn_index`
block), so the file cannot grow out of order even if the gate read is
skipped. Blocks raise `ContinuityGateError` carrying the reason.

### Self-ask/self-answer guard: no persisted delta = protocol violation

`append()` rejects a record whose `delta.summary` is empty/whitespace with
`TurnRecordError` naming the protocol violation. Per the SKILL prose, a turn
where nothing changed is not recorded as a silent alignment turn — the agent
runs reconnaissance instead (existing clause) rather than fabricating a
user-side answer.

### Hook refresh is additive and fail-open

In `lifecycle_hook.py`, a defensive import (relative → flat → `None`) keeps
standalone skill-packaged execution working — the package ships
`lifecycle_hook.py` but not the new module (the build manifest is not this
change's file scope), so packaged execution degrades to no refresh. The
helper resolves the active run via the existing `_active_run`, refreshes only
when a record file exists or the resolved run phase is `alignment`, and never
raises into the observe path. Verdict statuses: `validated` / `missing` /
`invalid` (with reason). Existing behavior — prompt signals, #503 research
re-entry routing, binding statuses, debug traces — is byte-for-byte
unchanged when no run/record is involved.

### Prompt layer wording: record-or-block

The canonical templates gain the enforcement sentence in the same bullet
(persistence clause only, per file ownership): before composing an alignment
move, load the persisted record and ground the move in it; append the turn
record before responding; a missing or stale record blocks the turn
(fail-closed); a turn introducing no persisted delta is a protocol violation.

## Rejected Designs

- **Per-turn one-file-per-record JSON blobs in a directory** (mirroring the
  hook `events/` store): the issue asks for a state file that *grows per
  turn* and a gate that reads *the* record; a directory scan makes
  continuity ordering implicit and orphan-prone. JSONL keeps append-only
  growth with total order in one file.
- **Storing the record inside the alignment SQLite graph**: `alignment_graph.py`
  is owned by #496/#491 in parallel, the graph only persists when the
  controller reference flow is explicitly run, and the issue's target is the
  agent's conversational turns — a workspace file readable without the
  reference flow. (The file is the bridge artifact #489 can reconcile into
  the graph later.)
- **Duplicating contract terms / trace schema locally**: the seam module is
  the only enumerated space (ADR-008); duplicating its schema would fork the
  registry the engine verifies against.
- **Making the hook block the host session on a failed gate**: the lifecycle
  hook's fail-open contract (issue #453, kept by #492/#503) never blocks the
  host; a hook-side block would also fire on non-alignment prompts. The
  fail-closed gate lives in the record protocol (`check_continuity` /
  `append`), which the prompt layer must call (record-or-block prose) and
  #489 will wire into the emission loop.
- **Time-based staleness (record older than N seconds)**: wall-clock decay
  would block legitimately paused sessions and pass fast fabrications; the
  structural turn-adjacency check captures exactly "an exchange happened
  without a record".
- **Requiring `contract_terms` on every record**: emission is unwired until
  #489; requiring it would make the record unwritable today. Optional-but-
  verified keeps the record honest now and contract-checked later.

## Risks / Trade-offs

- [Agent skips the gate read] -> `append()` still enforces adjacency and
  delta presence, so an ungated turn leaves either a blocked append or a
  detectable gap; #489 wires the gate into the emission loop for the hard
  guarantee.
- [Hook refresh writes a receipt into user runs] -> one small JSON file in
  the run's own `alignment/` directory, atomic, fail-open; written only when
  the directory already exists (no mkdir side effects on foreign runs).
- [Packaged execution cannot refresh] -> defensive import degrades to no-op
  verdict suppression; documented limitation, checkout execution (the
  enforced path) is unaffected.
- [Generated packages carry the new hook code and prose] -> regenerated in a
  generated-only commit via `build_skill_packages.py`; parity gate enforced.

## Migration Plan

No existing data to migrate: the record file is new; absence of the file is
the opening-turn state (`next_turn == 1` allowed). Existing runs without the
file behave exactly as before (hook refresh reports `missing` only when an
alignment phase or record file makes it relevant). No API removals.

## Open Questions

- None blocking. (#490 will define how the five prompt-signal categories map
  onto the recorded response class; the record's field is ready to carry it.)

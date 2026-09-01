# v2 follow-up — CLI-only operator journey (#470, gates 4/8 closure evidence)

Executed 2026-09-01 against `feat/issue-470-operator-facade`. Purpose: prove
that the operator surface alone — no Python API calls, no in-process
coordinator access — can carry one governed run from `prepared` through
`initialize` to a confirmed strategy, and render the operating
model, and that the shipped (packaged) alignment controller executes its own
`record` path.

Method: one fresh workspace (`.journey-workspace`), one governed run
(`run-operator-facade`, project `proj-facade`). The operator authors six
plain JSON documents in the workspace; every runtime step below is a CLI
verb. Commands are shown in the documented form (`uv run --frozen
research-tree …`, `uv run python -m research_tree.alignment_graph …`); the
captured transcript drove the identical entry points. Raw transcript and
workspace retained on the evaluation machine beside this file
(`.journey-transcript.txt`); this document quotes its outputs unedited
(excerpts marked with `…`).

## Operator document inventory

Authored before any runtime step — all product-facing documents, no internal
payloads:

| Document | Feeds CLI verb |
| --- | --- |
| `docs/graph.json` | `alignment_graph plan` (nodes/edges per `alignment_graph schema`) |
| `docs/brief.json` | `initialize --brief` (inputs, intent analysis, Working Brief fields) |
| `docs/blueprint.json` | `initialize --blueprint` (target id, one slot, initial change) |
| `docs/frame.json` | `initialize --frame` (decision frame: wording, primary decision, hypothesis) |
| `docs/projection.json` | `strategy propose --projection` (base projection; the product computes the display payload, digest, and content hash) |
| `docs/alignment-verification.json` | `strategy propose --alignment-verification` (independent subagent restatement) |

## Step 1 — create the durable governed run

```
$ uv run --frozen research-tree run --host claude \
    --workspace .journey-workspace --project-id proj-facade --run-id run-operator-facade \
    --outcome "Prove the operator CLI journey reaches the strategy gates." \
    --scope "One governed run driven end to end from CLI verbs." \
    --authority "Autonomous research after the human confirms the displayed strategy." \
    --success-oracle "The initialized run confirms the displayed strategy without any Python API call."
```

```json
{"command": "run", "status": "prepared", "readiness": {"failure_reasons":
["authority_binding_required", "alignment_confirmation_required",
"independent_reviewer_receipt_required", "readiness_canonical_unreachable"], "ready": false}, …}
[exit 0]
```

The run is honestly `prepared` and non-authoritative; the four named reasons
are exactly the v2 blockers this journey then closes one by one.

## Step 2 — confirm the alignment graph (human authorization, digest-gated)

```
$ uv run python -m research_tree.alignment_graph --workspace .journey-workspace \
    --project-id proj-facade init --run-id run-operator-facade            [exit 0]
$ uv run python -m research_tree.alignment_graph --workspace .journey-workspace \
    --project-id proj-facade plan --run-id run-operator-facade --graph-file docs/graph.json
    → "action": "await_human_confirmation", "alignment_digest": "f9a6…"   [exit 0]
$ uv run python -m research_tree.alignment_graph --workspace .journey-workspace \
    --project-id proj-facade confirm --run-id run-operator-facade \
    --confirmation "I confirm the stated outcome and authorize autonomous research within that scope." \
    --expected-digest 0000000000000000000000000000000000000000000000000000000000000000
    → "alignment graph changed after the displayed handoff draft"         [exit 1]
$ uv run python -m research_tree.alignment_graph --workspace .journey-workspace \
    --project-id proj-facade confirm --run-id run-operator-facade \
    --confirmation "I confirm the stated outcome and authorize autonomous research within that scope." \
    --expected-digest f9a6…                                                [exit 0]
    → "status": "autonomous", "phase": "research"
```

The wrong-digest confirmation attempt was executed deliberately and rejected
with the named graph-level reason — fail-closed, matching the v2 gate 1
verdict.

## Step 3 — initialize: the bind bridge (v2 F1 closure)

Re-run guidance: on a late-stage failure, re-run with the same idempotency key to resume. Re-running with a DIFFERENT key on an already-initialized run is rejected by contract (`run_already_initialized`); the same-key resume is the convergence path.

One verb now performs what v2 found unreachable: handoff resolution,
blueprint-target compilation **with the compiled handoff bound as a parent**,
`coordinator.initialize`, and decision-frame persistence.

```
$ uv run --frozen research-tree initialize \
    --workspace .journey-workspace --project-id proj-facade --run-id run-operator-facade \
    --brief docs/brief.json --blueprint docs/blueprint.json --frame docs/frame.json \
    --idempotency-key journey-init
```

```json
{"command": "initialize", "status": "initialized", "rev": "11", "result": {
  "state": "alignment",
  "frame_ref":     {"artifact_id": "frame-operator-cli", "revision": 1, …},
  "handoff_ref":   {"artifact_id": "alignment-handoff-d66141cc7d", "revision": 1, …},
  "target_ref":    {"artifact_id": "blueprint-target", "revision": 1, …}}, …}
[exit 0]
```

The blueprint target's `parent_refs` now carry the brief, the intent model,
and the exact `alignment-handoff-d66141cc7d@1` revision — the lineage
`coordinator.initialize` demands, produced at compile time by
`CanonicalBlueprintTargetCompiler.compile(alignment_handoff=…)` instead of a
harness-side ledger append.

Negative control (separate scratch run): `initialize` without any brief
document and no brief in the ledger fails with `working_brief_missing`
(exit 2). The bridge does not invent missing authority inputs.

## Step 4 — strategy propose (draft + independent verification)

```
$ uv run --frozen research-tree strategy \
    --workspace .journey-workspace --project-id proj-facade --run-id run-operator-facade \
    propose --projection docs/projection.json \
            --alignment-verification docs/alignment-verification.json
```

```json
{"command": "strategy.propose", "status": "proposed", "result": {
  "projection_ref": {"artifact_id": "strategy-journey", "revision": 1, …},
  "status": "draft"}, …}
[exit 0]
```

The CLI binds the recomputed authority fingerprint and the stored projection
reference into the verification document before registering it, so the #462
display gate sees a coordinator-grade binding rather than operator-declared
text.

## Step 5 — strategy display

```
$ uv run --frozen research-tree strategy \
    --workspace .journey-workspace --project-id proj-facade --run-id run-operator-facade display
```

```json
{"command": "strategy.display", "status": "displayed", "result": {
  "display_digest": "a3cd89aa5d6cd967d345059719336f4c2e5bb91ec89830c65bc41c989f1b4819",
  "goal_decomposition": [ … ], …}}
[exit 0]
```

## Step 6 — strategy confirm (digest-bearing human authorization)

```
$ uv run --frozen research-tree strategy \
    --workspace .journey-workspace --project-id proj-facade --run-id run-operator-facade \
    confirm --confirmation "I accept the displayed digest a3cd89aa5d6cd967d345059719336f4c2e5bb91ec89830c65bc41c989f1b4819 and authorize the research."
```

```
<rt:tool-output source="research-tree-cli" command="strategy.confirm" rev="18">{"command": "strategy.confirm", "status": "confirmed", "result": {
  "display_digest": "a3cd89aa5d6cd967d345059719336f4c2e5bb91ec89830c65bc41c989f1b4819",
  "projection_ref": {"artifact_id": "strategy-journey", "revision": 2, …},
  "state": "autonomous_research"}, …}</rt:tool-output>
[exit 0]
```

`prepared → initialized → displayed → confirmed → autonomous_research`,
entirely through CLI verbs. The generic-acknowledgement guard, the digest
gate, the authority-fingerprint gate, and the independent-verification gate
all sat between the operator and this receipt and were passed on their own
terms.

## Step 7 — operating-model view (v2 integrator gap closure)

```
$ uv run --frozen research-tree operating-model \
    --workspace .journey-workspace --project-id proj-facade --run-id run-operator-facade
```

```markdown
## Operating Model

Run facts for the operating model: fields carry this run's artifacts,
baseline-run dimensions carry measured baselines, not commitments.

### Roles
- Research owner: …
  - Handoff: …
- Platform integrator: …
  - Handoff: …
- Governance auditor: …
  - Handoff: …

### SLA (baseline run)
- Basis: baseline run — measured baseline, not a commitment. …
### Concurrency limits (baseline run)
- Basis: baseline run — measured baseline, not a commitment. …
### Blockers
| Obligation | Resolution action | Owner role |
| --- | --- | --- |
| … | … | … |
### Outcome layers
- Confirmed projection: strategy-journey@2 (display digest a3cd89aa…, authority fingerprint …)
…
### Fallback plan
- …
```

Roles, SLA, concurrency, blockers (coordinator-owned, mirrored verbatim),
outcome layers (now naming the confirmed projection from step 6), and the
fallback plan — readable without opening `delivery.py`. `--json` emits the
same model as the canonical payload.

## Step 8 — packaged `record` proof (v2 F2 closure)

The shipped Codex-package controller — the layout where v2 saw
`ImportError: attempted relative import with no known parent package` —
records a speech act in a real subprocess:

```
$ python packages/codex/research-tree/scripts/alignment_controller.py \
    --workspace .journey-workspace --project-id proj-facade record \
    --run-id run-operator-facade --node-id question-operator-cli \
    --outcome answered --fingerprint journey-turn-1
{
  "next_action": "plan",
  "stagnant_turns": 0,
  "state_changed": true,
  "turn": 1
}
[exit 0]
```

`speech_acts.py` now ships beside the controller and the lazy imports fall
back to the sibling module when the package context is absent; the packaged
surface executes its own alignment protocol.

## Verdict against the v2 findings

| v2 finding | Status in this journey |
| --- | --- |
| F1 (HIGH): `prepared → initialized` unreachable from any surface; strategy gates cut off | **Closed** — steps 1–6 complete the chain via CLI verbs; the bind is a compile-time handoff parent, not a harness-side write |
| F2 (HIGH): packaged `record` crashes on the speech-act import | **Closed** — step 8, rc 0 in the shipped layout |
| Integrator: operating model invisible to operators | **Closed** — step 7, markdown + `--json` |

## Honest boundaries

- No host subprocess was driven; the lifecycle hook and host execution lanes
  are out of this journey's scope (unchanged from v2).
- Delivery compilation (Technical Research Package / Human Research Report)
  was not executed in this run; this journey ends at confirmed strategy plus
  the operating-model view. Work items, finding packs, and delivery remain
  in-process surfaces for the next batch.
- The operating-model SLA/concurrency/adoption numbers are baseline-run
  dimensions by design — labeled, never commitments.
- The alignment graph was confirmed through the `research_tree.alignment_graph`
  CLI module entry point, the same `main()` the shipped controller wraps.

# Alignment Graph Controller

Use `scripts/alignment_controller.py` before strategy handoff. It persists the
requester's and agent's changing beliefs as a temporal heterogeneous multigraph;
it does not create or display a Research Tree during alignment.

## Storage model

One run owns `.research-tree/projects/<project-id>/runs/<run-id>/alignment/alignment.db`. SQLite uses WAL,
foreign keys, full transaction synchronization, and a busy timeout. The schema
contains:

- `nodes`: the current materialized node view;
- `edges`: independently identified directed relations, including parallel
  relations between the same nodes;
- `controller`: turn, pending question, last decision, and handoff state; and
- `events`: append-only full-state revisions used to rebuild the materialized
  view after corruption or interruption.

Node types include human and agent beliefs, intent hypotheses, outcome, intended
use, scope boundary, delivery, authority, success oracle, feasibility,
constraints, unknowns, evidence, disagreements, strategy, and decisions. Edge
types include `asserts`, `supports`, `contradicts`, `limits`, `refines`,
`supersedes`, `depends_on`, `answers`, `informs`, and `derived_from`.

Do not overwrite competing beliefs into one statement. Give every node and edge
a stable ID and update its status; the event log preserves earlier revisions.
Do not store prompts, transcripts, secrets, or credentials in the graph.

## Planning one alignment turn

Before a user-facing question, merge a bounded graph update and run `plan`.
The controller returns exactly one of:

- `ask_one`: one high-impact unresolved node that only the requester can settle;
- `reconnaissance`: required knowledge is agent-verifiable, stale, or missing;
- `await_human_confirmation`: the graph supports a visible strategy projection.

The readiness gate requires supported outcome, intended use, scope boundary,
delivery, authority, success oracle, feasibility, and strategy nodes; no
requester-only gap or high-impact dispute may remain. At least one executable
research question must exist and each must carry a closure oracle. Supported
evidence must carry `attributes.anchor.kind` and `attributes.anchor.ref`. It
must reach a current research question through active graph relations, or be
explicitly marked `attributes.handoff_disposition: alignment_only`; evidence is
never silently discarded.

Render a short turn with a current mirror, one useful fact or counterargument,
its decision consequence, and at most one open-ended question. The controller's
internal node list is not a questionnaire or a user-facing deliverable.

## Confirmation and compilation

When `await_human_confirmation` is returned, show a compact strategy projection
from the Alignment Graph, not a Research Tree. Pass the displayed
`alignment_digest` back to `confirm`; a changed graph invalidates stale
confirmation. A generic acknowledgement is insufficient, while an explicit
contextual instruction accepting the displayed strategy and autonomous handoff
is valid.

After confirmation, `compile` atomically writes `handoff.json` in the alignment
run directory by default and projects:

- accepted outcome and strategy into the handoff artifact;
- open agent-researchable unknowns into Decision Slots;
- their closure oracles into validation rules; and
- the confirmed outcome, intended use, scope, delivery, authority, success
  oracles, feasibility, constraints, and strategy into execution context;
- closure oracles into every worker-facing frontier action; and
- anchored reconnaissance evidence, including indirect `supports`, `limits`,
  `refines`, and related paths, into deduplicated Finding Packs that initialize
  the Research Tree as a zero-realized-delta baseline.

An active `supersedes` edge removes the target research obligation from the
compiled tree. Historical baseline evidence never marks the landscape action
complete; workers must still map, challenge, and validate the decision.

Only this compilation boundary creates the Research Tree. Normal research after
handoff remains autonomous unless new evidence crosses authority or safety
boundaries.

## Python runtime

The commands below are source-checkout commands and must run in the repository's
locked `uv` environment. Run them from the checkout root with
`uv run --frozen python`; never replace that prefix with the system `python`
executable. If the controller is loaded from an installed skill directory,
locate the `research-tree` checkout first and pass it to
`uv run --project <checkout> --frozen python <skill-dir>/scripts/alignment_controller.py`.
Without a discoverable `uv` project, stop with an environment diagnostic rather
than invoking the bundled script under an arbitrary interpreter.

## Commands

```bash
uv run --frozen python scripts/alignment_controller.py --workspace . schema \
  --output alignment-update.example.json
uv run --frozen python scripts/alignment_controller.py --workspace . --project-id <project-id> init --run-id r1
uv run --frozen python scripts/alignment_controller.py --workspace . plan \
  --project-id <project-id> --run-id r1 --graph-file alignment-update.json
uv run --frozen python scripts/alignment_controller.py --workspace . record \
  --project-id <project-id> --run-id r1 --node-id intended-use --outcome answered \
  --fingerprint compact-model-state-v2
uv run --frozen python scripts/alignment_controller.py --workspace . confirm \
  --project-id <project-id> --run-id r1 --expected-digest <displayed-digest> \
  --confirmation "I accept this strategy and authorize autonomous research."
uv run --frozen python scripts/alignment_controller.py --workspace . --project-id <project-id> compile --run-id r1 \
  --output .research-tree/projects/<project-id>/runs/r1/alignment/handoff.json
uv run --frozen python scripts/alignment_controller.py --workspace . --project-id <project-id> rebuild --run-id r1
```

Use `schema --output` on Windows PowerShell 5 instead of `Set-Content -Encoding
utf8`, which writes a BOM. Inputs and generated artifacts use strict UTF-8
without BOM. Unknown node or edge fields and unsupported enum values fail with
the accepted contract instead of being ignored.

The installed host packages contain a standalone copy backed only by Python's
standard library, but the agent must still select a supported interpreter or
the repository-managed `uv` project explicitly; a bare `python` invocation is
not a supported execution path.

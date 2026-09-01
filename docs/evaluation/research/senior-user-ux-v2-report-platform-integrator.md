# senior-user-ux-v2 — Track A report: platform engineering integrator

- **Identity:** `uxv2-integrator-b7e2` (independent, fresh context; agent-simulated role)
- **Date:** 2026-09-01 · **Workspace:** `D:/codebase/research-tree-worktrees/v2-run-lane` (all commands `uv run --frozen`)
- **Baseline:** senior-user-ux-20260820 platform-integrator 65/100 (isolated pilot viable; org-wide rollout not approved)

## Score: 64/100 — isolated install story is now solid; operator-operated lifecycle is not

| Dimension | Weight | Score | Weighted |
| --- | --- | --- | --- |
| Installation success ×3 hosts | 25% | 9/10 | 22.5 |
| Host isolation | 15% | 9/10 | 13.5 |
| Lifecycle ergonomics | 20% | 5/10 | 10.0 |
| Operator-grade surfaces (no leakage) | 20% | 6/10 | 12.0 |
| Adoption readiness (gate-4/gate-8) | 20% | 3/10 | 6.0 |

The headline improvement: the 8/20 "install-status conflicts after verified copy-installs" defect
did **not** reproduce — every host install is byte-verified, digest-verified, and status-consistent.
The headline regression risk remains exactly where the 8/20 run put it: an ordinary operator still
cannot complete the alignment/confirmation flow or reach the operating-model view without reading
source and calling internal Python APIs.

## Install matrix (copy-install, isolated temp homes)

| Host | Override used | Install | `diff -qr` vs source | setup status | doctor |
| --- | --- | --- | --- | --- | --- |
| Codex | `--codex-home <tmp>` | installed, hooks.json current | exit 0 vs `packages/codex/research-tree` | current, `payload_digest_match` (bd4878dc…) | healthy, ready |
| Claude Code | `--home <tmp>` | installed, .claude/settings.json current | exit 0 vs `packages/claude-code/research-tree/skills/research-tree` (naive diff vs package root mismatches — payload is nested) | current, `payload_digest_match` (7bd577cd…) | healthy, ready |
| Hermes | `--home <tmp>` (no `--hermes-home` flag; shared flag resolves `<home>/.hermes`) | installed, .hermes/config.yaml current | exit 0 vs `packages/hermes/research-tree` | current, `payload_digest_match` (9d843484…) | healthy, ready |
| Negative | `--codex-home <empty>` | n/a | n/a | `missing` / `target_missing` (correct fail-closed) | n/a |

Status verdicts agreed with byte-level diffs on 3/3 hosts. Both status and doctor honestly report
`activation_state: static_ready`, `live_activation: unproven`. Each temp home contained only its own
host's tree — no cross-host bleed. Deduction: for Claude, the obvious verification (`diff -qr` package
root vs target) mismatches because the package nests the payload under `skills/research-tree` plus a
`.claude-plugin` dir; no doc states the payload source path used for the digest.

## Journey log (operator surface unless noted)

1. **Discover hosts** — README/operator guide make codex|claude|hermes and `research-tree-setup` clear.
   The CLI exposes seven commands; `strategy` appears in no guide (0 grep hits in `docs/guides/`).
2. **Install ×3** — all succeeded; JSON result with per-installation action and hook state; clean dry-run plans.
3. **Verify installs** — status digest-verified per host; doctor healthy; negative and isolation checks correct.
4. **`run`** — prepared a bounded drift-study run (`--outcome/--scope/--authority/--success-oracle`, all plain-language
   inputs, good design). But: stderr `runtime_readiness_canonical_unreachable: run is not initialized` on
   **every** subsequent command, and readiness lists four codes with no remedy path.
5. **`status`** — `blocked`; later (after strategy work) 12 failure reasons including internal bookkeeping keys
   `p0_closure_tokens`, `insight_ref`, `readiness_ref`, `evaluation_ref`, `technical_delivery_ref`,
   `goal_satisfaction`, `independent_delivery_review`, `human_delivery_ref`, `acceptance_ref`. No gloss.
6. **`resume`** — returned `status: resumed` on a run whose alignment was never confirmed (appends a
   `lifecycle-resume` artifact). Operators cannot distinguish durable-state bookkeeping from progress.
7. **`verify`** — `unmet_obligations` with `host_id: null, package_id: null`; honest fail-closed, zero explainability.
8. **`strategy propose`** — requires a projection JSON whose schema exists only as a dataclass
   (`strategy_projection.py`, 15+ fields incl. ArtifactRefs). Error for `{}`: `strategy_projection_invalid`,
   `next_action: null`. The 8/20 `uv run python` + controller-paths finding reproduces here.
9. **Internal-API attempt (disclosed)** — only via `RunLedger.append_artifact` (alignment-handoff, then
   blueprint-target *with parent lineage*), `coordinator.initialize`, `persist_decision_frame`,
   `persist_strategy_projection`, `write_alignment_verification` (distinct verifier identity enforced —
   good guard) did the run reach displayable state (scratch/attempt_flow2.py).
10. **`strategy display`** — worked from the CLI once the internal chain existed: `displayed`,
    `display_digest: b8098859…`.
11. **`strategy confirm`** — digest-quoted, non-generic confirmation text **rejected**:
    `alignment_not_confirmed`, no reason. Source shows `AlignmentGraphStore.compile_handoff()` requires a
    populated graph (controller `autonomous`, matching alignment digest, an accepted strategy node with
    tracks, a closure oracle on every research node) that **no CLI surface generates**. Not completed (time-boxed).
12. **Operating-model view (gate-8)** — the seven operator fields (roles, SLA, concurrency limits,
    blockers with owners/resolve conditions, outcome layers, adoption metrics, fallback) are implemented in
    `delivery.py` (`_operating_model`, `_render_operating_model`; exactly-three-roles validation) but have
    **zero references in `cli.py`**. No operator command reaches them.

## Findings (ranked)

1. **HIGH — Alignment/confirmation flow unreachable from operator surfaces (gate-4).** No CLI path creates
   the prerequisites; schema undocumented; confirm then fails without a reason. An org cannot certify an
   operator runbook around this.
2. **HIGH — Human Research Report operating model not operator-reachable (gate-8).** Implemented, validated,
   rendered — but only inside delivery, which the CLI journey cannot itself complete.
3. **MEDIUM — Internal bookkeeping schema leaks to operators.** Obligation codes above, `authority_revision`
   counters, `rt:tool-output rev` attributes, persistent stderr condition line, `next_action: null` everywhere.
4. **MEDIUM — `resume` reports success on a never-confirmed run** (semantics conflate bookkeeping with progress).
5. **LOW — Claude package layout traps naive verification** (payload nesting undocumented).
6. **LOW — Run workspace scaffolds all three hosts' configs even when one host is selected.**
7. **INFO — 8/20 install-status-conflict defect fixed/absent**: byte-diff, digest, status, and doctor agree 3/3.

Counterweights (creditable): digest-verified status instead of path trust; honest `live_activation:
unproven`; correct `missing` detection; safe error envelopes (no secrets/stack traces); distinct-verifier
enforcement on alignment verification; generic-"yes" confirmation rejected by design.

## Noise accounting (three-component protocol)

1. **Input-token visibility in receipts: not visible.** No command in this journey reported token usage or
   a budget receipt; the product surface exposes no accounting basis (host-side session accounting is
   external to the product). Component 1 is reported, not estimated.
2. **Duplicate reads/commands I experienced: 6** of ~38 issued commands (one arg-order retry, one
   environment-relocation reissue, four API/path retries during the internal-API attempt). Every duplicate
   was a *command* retry; none was a *document reread*.
3. **Rereads of confirmed material without digest/scope change: 0.** operator.md, agent guide, skill
   templates, baseline/oracles: each read once.

## Disclosures

- Agent-simulated role; no human requester; confirm text authored by the evaluating agent.
- The internal-API attempt is itself the finding being reported; it replicates `tests/strategy_support.py`
  patterns in scratch scripts under `track-a/platform-integrator/scratch/`.
- `strategy confirm` not completed (alignment-graph prerequisites time-boxed out) — recorded incomplete.
- Mid-run the evaluation environment relocated my scratch tree; the first workspace ledger was recreated
  empty and the run was re-created at the relocated path (one duplicate command, counted above).
- Independence: track-b artifacts and all other `senior-user-ux-v2-report-*.md` files were never read.
- No repository source modified; writes limited to my three output files plus scratch.
- Source files were read to document schema/reachability claims (cited inline: `skill_setup.py`,
  `cli.py`, `coordinator.py`, `alignment_graph.py`, `strategy_projection.py`, `delivery.py`).

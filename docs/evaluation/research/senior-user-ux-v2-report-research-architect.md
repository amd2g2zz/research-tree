# senior-user-ux-v2 — Research Architect role report (Track A)

- **Identity**: uxv2-architect-a41c (independent, fresh context; agent-simulated senior research architect)
- **Track**: A (senior-user-ux-v2, #292/#451); workspace `D:/codebase/research-tree-worktrees/v2-run-lane` @ 6d3996a
- **Date**: 2026-09-01; protocol per 8/20 baseline (#292); raw notes: `transcript-notes.md` alongside this file

## Score: 68/100 (conditional use for bounded pilots only; do not adopt for operator-facing research runs until the lifecycle middle is fixed)

Baseline comparison: 8/20 research-architect = 76/100. This run scores lower on operator lifecycle substance, higher on install honesty; no noise regression observed.

### Dimension breakdown (weighted)

| Dimension | Weight | Score | Rationale |
| --- | --- | --- | --- |
| Alignment quality | 25% | 70/100 | Mechanically real Socratic loop: vague brief → `reconnaissance` with 9 named gaps, never guessed; requester-only ambiguity → `ask_one` ("highest-impact unresolved point that only the requester can settle"); readiness gate enumerates every missing supported dimension; confirm requires digest-bearing contextual confirmation; `compile` before confirm fails `stale_handoff_confirmation` (fail-closed). Deductions: packaged `record` crashes (ImportError), `record answered` reports success without transitioning the node, `disputed` status accepted at input but rejected by the transition table, displayed digest ≠ stored digest after confirm. |
| Evidence-boundary honesty | 25% | 90/100 | Best dimension. Every failure is named and fail-closed: 4 canonical readiness reasons on `run`; `verification_failed` + `canonical_conflict` + "run is not initialized" on `verify`; `prepared`/`resumed` explicitly non-authoritative; copy-install returns `live_activation: "unproven"`; strict schema validators print allowed values. Minor deduction: doctor payload internally inconsistent (install `current` yet `hosts.claude.state: "unknown"`); `record` success-shaped receipt hides a non-transition. |
| Research output usefulness | 20% | 40/100 | No Technical Research Package, Human Research Report, or Living Brief was produced: the run never reached execution because the CLI strategy gates are unreachable (see F1). The alignment layer did compile a real handoff.json, and the journey itself surfaced a grounded answer to my research question (ledger-first canonical reads), but that was my analysis, not a product deliverable. |
| Recovery/correction substance | 15% | 50/100 | `status`/`verify`/`resume` all echo canonical revision and identical named reasons; unknown states are explicit; stale/digest checks reject honestly. But recovery cannot repair the observed state: `resume` re-derives the same blockers, and no documented command can initialize the run; the correction protocol's `record` path is broken in the installed package (F2). |
| Host isolation | 15% | 80/100 | Copy-install is digest-verified and self-contained; hooks fail-open and stay inert without an active binding; package treated as read-only with workspace-scoped state; `--home` scoping works and default doctor honestly conflicts against pre-existing real-home installs rather than silently overwriting. Deduction: no warning that `install` without `--home` would target the real user home. |

### Journey log (commands → outcomes; full detail in transcript-notes.md)

1. INSTALL: `research-tree-setup install --host claude --mode copy --home <sim>` → installed, hooks current; `setup status` → `current`/`payload_digest_match`, `live_activation: unproven`. No post-copy-install conflict (baseline defect not reproduced). `doctor --host all` (default home) → honest 3x `link_target_mismatch` conflict; scoped doctor → `healthy`.
2. LIFECYCLE: `research-tree run` (outcome/scope/authority/success-oracle all stated) → status `prepared`, readiness false with 4 named reasons.
3. ALIGNMENT: graph init/plan; vague brief → `reconnaissance` (no guess); requester-only gap → `ask_one`; 5 merge rounds to `await_human_confirmation` (digest 573a6c76…); digest-bearing `confirm` → autonomous; `compile` → handoff.json. **`record` crashed with ImportError on the documented invocation**; workaround (module-mode + copying the unpackaged `speech_acts.py` into the temp install) revealed a second-layer `AuthorityTransitionError` on status `disputed`.
4. STRATEGY GATES: `strategy propose` (valid projection authored via the product's own API) → `invalid_input: run is not initialized`, **unresolvable from any documented surface**; `initialize_research_from_alignment` writes `research-tree-state` but the coordinator requires `research-run-state` created only by `coordinator.initialize`, which needs a blueprint-target lineage no CLI subcommand produces.
5. EXECUTION/DELIVERABLES: none reached. Run ends `blocked`; `verify` honestly reports `verification_failed`/`canonical_conflict`.

### Findings (ranked by severity)

- **F1 (HIGH) — Operator lifecycle has a broken middle.** A `prepared` run cannot reach `initialized` through the CLI or the installed skill: `strategy propose/display/confirm` all fail "run is not initialized" even after a fully digested alignment confirmation and compiled handoff. The bridge (`coordinator.initialize` needing alignment-handoff + blueprint-target ledger artifacts) exists only as an undocumented Python chain. Evidence: exact commands and `<rt:error>` payloads in transcript-notes §4. This is a regression-shaped gap against the "stable lifecycle interface" promise in README.
- **F2 (HIGH) — The installed package cannot execute its own alignment protocol.** Documented invocation `python scripts/alignment_controller.py … record` crashes: `ImportError: attempted relative import with no known parent package` (`from .speech_acts import …`, alignment_controller.py:331). `speech_acts.py` is absent from the packaged `scripts/`, and a relative import cannot work under direct-script execution regardless — the shipped surface is structurally broken for `record`.
- **F3 (MEDIUM) — Success-shaped non-transition.** `record --outcome answered` returns `state_changed: true, turn: 1, next_action: plan` while the human-only node silently remains `candidate` (speaker_role is agent; only human-origin merges promote it). Defensible authority model, dishonest receipt shape.
- **F4 (MEDIUM) — Repeated canonical block.** The identical readiness-failure + full-request JSON block is echoed by `run`, `resume`, `status`, and `verify` (4 repeats, no digest change), each preceded by a stderr prelude line. Against the spirit of the zero-reread clause on the product side.
- **F5 (LOW) — Rough edges.** Doctor payload self-inconsistency (current vs unknown); `setup status` lacks `--mode` while `install` accepts it; graph-file path resolves relative to workspace, not cwd (error message helps); displayed alignment digest ≠ stored handoff digest after confirm; `strategy` requires parent flags before the subcommand (argparse error otherwise).
- **F6 (POSITIVE) — Honesty is real.** Strict input validation with allowed-value lists, fail-closed compile/confirm/verify, non-authoritative receipts, `live_activation: unproven`. The product refuses to fake completion at every layer I could reach.

### Noise accounting (three-component protocol)

1. **Input-token volume**: **not visible to role.** No runtime receipt, budget artifact, or token count appeared in any command output, and lifecycle hooks were not active for this session, so the 70%-of-14,071,408 proxy check cannot be self-measured. I state this rather than invent a number.
2. **My duplicate reads**: 3 total (one overlapping coordinator.py region read after an awk sweep; one repeated `--help`; one `strategy propose` re-run after an argparse placement error). Three malformed graph-file submissions were self-inflicted and were caught by the product's validators — not counted as product noise.
3. **Confirmed-material rereads**: 0. I never re-read already-confirmed docs/status without a digest or scope change.

**Direction vs 8/20 baseline narrative** (pervasive repeated reconnaissance, long status output, growing JSONL rereads): **materially quieter.** State is SQLite + bounded per-event JSON (no JSONL growth), failures are short named-reason payloads, and output blocks are compact — my estimate is a substantial reduction in repeated output (roughly 50–70% fewer repeated blocks than the baseline narrative implies). I cannot compute an exact percentage: the 8/20 run never produced a counted repeated-output baseline (declared in `senior-user-ux-v2-baseline.md`), and my run was shorter and blocked early, which biases toward quietness. Caveat recorded: F4 shows the product itself still repeats one block 4x.

### Disclosures

- I am an agent-simulated role (Claude agent), not the human role the protocol imagines; scoring is my independent judgment per the Track A rubric.
- I could not complete: strategy display/confirm via CLI, slot execution, deliverable production (TRP/Human Research Report/Living Brief), and the fresh-subagent restatement (Protocol 3 step 2) — the first three blocked by F1, the last by session budget; alignment-layer confirmation used the digest gate but lacked the independent-verifier receipt.
- The `record` workaround modified only my temp-dir copy of the installed package (`/tmp/tmp.zf62Af7c0O/uxv2-home`), never repository source.
- One coordinator interruption occurred mid-evaluation; I resumed per the original protocol without redoing completed steps.
- The GateGuard first-Write block described in the task did not trigger in this environment (both writes succeeded on first attempt); I flag its absence rather than simulate it.
- Exact noise percentage vs 8/20 is not computable and is not claimed.

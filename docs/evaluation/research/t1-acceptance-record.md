# T1 Acceptance Record — single closed loop & minimal canvas

> Issue #562 · Milestone #6 · 2026-10-31 · Capability-based: done = achieved
> Suite: **243/243 rt-core vitest** (tsc strict clean) + **1391 legacy Python** — all green.

## Exit criterion (roadmap T1)

2-3 real ideas end-to-end + H1/H3 first data.

## The three ideas (test/t1_closeout.test.ts)

| Idea | Shape | Path | Verdict |
|---|---|---|---|
| idea-fuzzy | divergence-heavy (3 branches, 3 slots, 1 claim) | A1 divergence check fires → A0 → headless → dual render → commit | GO |
| idea-crisp | direct (4 utterances) | A1 → A0 → headless → dual render → commit | GO |
| idea-doomed | make-or-break dies | early-termination PAUSE → bury → converge → commit | NO-GO |

## Checklist (issue #562)

- [x] #555 A1 full: four-way routing, corrections same-route, echo confirmation, convergence C1-C5 — `test/dialogue.test.ts` (18 cases)
- [x] #556 evidence engine L1-lite — `test/evidence.test.ts` (6 cases): weighted vote, independence collapse, quick-check
- [x] #557 EVSI three-action — `test/evsi.test.ts` (5 cases): EVSI/cost ranking, mob-first, replay disclosure, zero-cost guard
- [x] #558 single-seat verification — `test/verification.test.ts` (9 cases): method layers, counter-evidence quota fail-closed, honest promotion, search envelope
- [x] #559 minimal canvas — `test/canvas.test.ts` (8 cases): same-source render, five write gates, park revival mandatory
- [x] #560 dual rendering — `test/dual_rendering.test.ts` (8 cases): 7-section report, 底稿 schema v1, same-source
- [x] #561 decomposition viz + artifact management — `test/card_wall.test.ts` (7 cases): provenance cards, delete, 待对齐 placeholders, checklist-gated confirm, deleted_nodes → freeze
- [x] #580 TUI — `test/tui_renderer.test.ts` (5 cases): same-source frame, red-line labels
- [x] Three-idea e2e — `test/t1_closeout.test.ts` (7 cases): A1 → A0 → headless → dual rendering → version commits → MCP verdicts; multi-task coexistence; chain integrity

## H1/H3 first data (engine-side projections)

- **H1 proxy (intake effort)**: the A1 routing receipts (slot/parking-lot/claim counts) quantify what the user had to express — the LLM-side comparison vs Deep Research consumes these counts in keyed sessions (#588).
- **H3 proxy (底稿 handoff shape)**: the deliverable's capability_outline / constraints.hard / unverified_assumptions are the structure the implementation agent consumes — verified non-empty for all three ideas. The LLM-side measurement (agent startup quality from the 底稿 vs essay) rides keyed sessions.

## Honest gaps

- **LLM-side H1/H3 measurement**: needs keyed sessions (#588 provisioning). The engine-side projections are the measurement data, not the measurements themselves.
- **Real-pi-host e2e**: the T0 record (#605/#606) covers the pi-host session; the T1 closeout re-uses the headless driver over the same machine — the pi-host walk composes at the next pi extension update.
- **Doomed idea's refute path**: c-wasm refutes but has no dependents to propagate to (single-claim fixture) — belief propagation is pinned in the mock e2e (#607) with a chain fixture.

## Verdict

**T1 exit criteria met (capability-based).** Milestone #6 (T1) ready to close; T2 wave opens.

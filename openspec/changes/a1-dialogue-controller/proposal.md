# a1-dialogue-controller

## Why

Issue #555 (T1 row 1, docs 01 A1): the per-turn pipeline — decompose (four-way route) → slot update → claim extraction → quick-check → convergence eval → next-step choice. The engine consumes model-side classifications and routes mechanically (two-layer contract #501); no privileged channel for corrections; convergence is computed, never felt.

## What changes

- `dialogue/controller.ts`: DialogueController —
  - **four-way routing**: preference → slots (authority), claim → ledger (verify), guess → hypothesis ledger (same footing), branch → parking lot;
  - **constraint provenance**: guessed constraints carry the discrimination question; discriminated-as-estimate relaxes to intents on the spot; deployment facts harden;
  - **corrections same-route**: preference change → comply + consequence map; private fact → ledger; guess restated → hypothesis re-review (on_trial);
  - **echo confirmation**: triggers only for kill-condition / feasibility-menu / verdict-structure changes;
  - **convergence C1-C5**: computed (C1 problem-shaped ∧ C2 key slots ∧ C3 make-or-break; C4 decay / C5 restatement pace);
  - **divergence**: branches ≥3 with ≤1 claim → upstream terrain proposal;
  - **intent model**: visible, versioned, history diffable.

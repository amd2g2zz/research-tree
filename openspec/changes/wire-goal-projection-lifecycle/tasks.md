# Wire Goal Projection Lifecycle — Tasks

## 1. Red Tests

- [x] 1.1 Add `tests/test_goal_wiring.py` with the named B1 contract tests: serves happy path,
      unknown target, unknown oracle, P0 requires oracle, goal decomposition projection.
- [x] 1.2 Add the R1 CLI lifecycle test (propose → display → confirm → tree bridge, digest
      guard rejects generic confirmation, serve validation fail-closed pre-confirm).
- [x] 1.3 Add the R3 falsifiability tests (oracle without evidence standards, dangling
      decision-target oracle reference → display rejected, run state unchanged).

## 2. Confirmed Projection Basis

- [x] 2.1 Add `strategy_projection.latest_confirmed` returning the projection revision named
      by the run's latest valid `handoff_confirmed` lifecycle event (digest-matched); fail-closed
      `None` otherwise.

## 3. Slot serves Validation (B1)

- [x] 3.1 Add required `serves` to the Decision Slot whitelist in `decision_map.py` (shape
      validation only: `target_id` identifier + `oracle_ids` identifier sequence).
- [x] 3.2 Validate serves at `CanonicalWorkItemCompiler.compile` against the run's confirmed
      projection with the exact contract messages, and carry `serves` on the work item payload.

## 4. Projection Lifecycle Wiring (R1)

- [x] 4.1 Add the `strategy propose/display/confirm` CLI verbs calling the existing coordinator
      APIs with `actor="human"` and the digest-in-confirmation guard.
- [x] 4.2 Pre-flight the confirmed alignment graph before confirm; bridge
      `initialize_research_from_alignment` after confirmation produces the research tree.
- [x] 4.3 Add the display-time falsifiability review (evidence-bound oracles, no dangling
      decision-target references) before any mutation.

## 5. Handoff Projection (B1)

- [x] 5.1 Record `confirmed: true` + `goal_decomposition` in the alignment-handoff payload.

## 6. Fixtures and Gates

- [x] 6.1 Update existing fixtures (slot serves, confirmed-projection setup) and run the full
      gates: pytest, ruff check/format, package check, openspec strict validation, docs and
      repository layout checks.

## 7. Review Hardening (alpha3 batch-3)

- [x] 7.1 Sink the falsifiability gate into the coordinator authority layer:
      `display_strategy` validates the projection revision it displays before the
      `alignment_projection_ready` transition (CLI pre-check retained as the message-
      fidelity layer); coordinator-level negative tests prove the persist→display→confirm
      bypass is closed with state, revision, and lifecycle-event immutability.
- [x] 7.2 Document the persist-status boundary: `persist_strategy_projection` accepts any
      valid projection status (status alone confers no authority) because display and
      confirmation carry the authority gates.
- [x] 7.3 Make `latest_confirmed` fail closed: a `handoff_confirmed` event that cannot be
      resolved and is not older than the last resolvable confirmation returns `None`
      instead of silently re-arming the older confirmation; a confirmed revision
      superseded by a later revision of the same projection is no longer returned
      (docstring-as-contract: the supersession sentence is now implemented, not rewritten).
- [x] 7.4 Document in `goal_decomposition` that Decision Slots without a serves link are
      skipped (legacy slots pre-#427 do not appear in the mapping).

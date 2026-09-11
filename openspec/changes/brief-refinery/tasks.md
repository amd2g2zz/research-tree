## 1. Tests (RED first)

- [x] 1.1 RED: extraction of a multi-statement brief yields atomic,
      clustered, typed objects with conservative defaults (model-requested
      hard-constraint downgraded to preference; duplicates/equivalent
      paraphrases merge; merged objects record `merged_into` and the
      survivor absorbs their anchors)
- [x] 1.2 RED: lifecycle illegal transitions rejected fail-closed naming
      the transition; parked reactivates to open; terminal states admit
      nothing
- [x] 1.3 RED: confirmation upgrade requires a confirmation reference and
      refuses without one; only the confirmation path produces
      hard-constraint
- [x] 1.4 RED: equivalence merge reuses the claims.py union-find surface
      (shared equivalence key merges a paraphrase with an existing object)
- [x] 1.5 RED: conflict-pair detection (same normalized topic, opposite
      polarity) is engine-deterministic
- [x] 1.6 RED: vagueness/conflict queries return registry-derived numbers
- [x] 1.7 RED: persistence round-trip with digest; tampered file fails
      closed on load
- [x] 1.8 RED: closure blockers name only confirmed hard-constraint
      violations; unconfirmed objects never block
- [x] 1.9 RED: registry changes convert into a turn-record delta payload
      consumable by AlignmentTurnRecordStore.append
- [x] 1.10 RED: malformed candidate rejected fail-closed (schema error names
      the offending candidate; the batch registers nothing)

## 2. Implementation

- [x] 2.1 `brief_refinery.py`: object schema, conservative defaults,
      lifecycle state machine, confirmation upgrade, conflict detection,
      signal queries, closure-blocker query, digest-persisted store
- [x] 2.2 claims.py: generic `cluster_identity_groups` (union-find);
      `cluster_provenance_components` delegates to it
- [x] 2.3 alignment_turn_record.py: additive `registry_delta` seam
- [x] 2.4 `__init__.py` additive exports

## 3. Gate

- [x] 3.1 full suite + ruff + delivery validate + openspec governance +
      skill-package parity → PR feat/issue-524-brief-refinery → dev
      (detect-changes + impact-scope reconcile before push)

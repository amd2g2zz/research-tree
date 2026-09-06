## 1. Tests (RED first)

- [ ] 1.1 RED: manifests-without-review stays blocked; passing review flips
      delivery_pending; stale digest rejected; non-independent payload
      rejected fail-closed
- [ ] 1.2 RED: failed review creates mandatory remediation node + reopens
      slot + records gate failure; gap with `revive_node_id` revives a
      discarded node (registry entry retained)
- [ ] 1.3 RED: pruned node lands in `discarded_evidence` with terminal
      reason, oracle, evidence need, slot, selection value; deduped by node id
- [ ] 1.4 RED: landscape slot with no recorded comparison never saturates on
      novelty 0; comparison recorded keeps the M6 coverage gate

## 2. Implementation

- [ ] 2.1 `independent_review.py`: `deliverable-quality-review` kind + role +
      `validate_deliverable_quality_review_payload` (identity pair, manifest
      digest binding, per-oracle verdicts, named-gaps contract)
- [ ] 2.2 `recursive_search.py`: `register_deliverable_quality_review` (stale
      digest rejection, pass → delivery_pending, fail → remediation nodes +
      slot reopen + revival), gate inside `finalize_research_delivery`
- [ ] 2.3 `recursive_search.py`: `discarded_evidence` registry in
      `prune_research_state`; coverage guard in `_slot_evidence_saturated`;
      init defaults
- [ ] 2.4 `tree_state.py`: two optional payload keys + shape validation
- [ ] 2.5 `__init__.py` exports

## 3. Gate

- [ ] 3.1 full suite + ruff + validate + governance + parity → PR
      feat/issue-495-deliverable-quality-gate → dev

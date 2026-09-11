## 1. Tests (RED first)

- [ ] 1.1 RED: deleted record file + intact event log → next turn proceeds
      with the `reconstructed` marker, degraded verdict + degraded receipt
- [ ] 1.2 RED: empty event log → block unchanged; corrupted event log →
      block; corrupt record file → block unchanged
- [ ] 1.3 RED: reconstructed record carries the enforced marker (schema
      rejects any `reconstructed` value other than true; authored records
      omit it); reconstruction path is the only writer
- [ ] 1.4 RED: single missing index with subsequent events heals from the
      log; contradictory histories (log behind the file, gapped turn axis)
      fail closed

## 2. Implementation

- [ ] 2.1 schema marker: `reconstructed` field, `from_dict`/`to_dict`
      presence rules (additive, authored payloads byte-identical)
- [ ] 2.2 read-only event-log reader + baseline synthesis (grounded mirror,
      event delta, validated traces) with the contradiction rules
- [ ] 2.3 `reconstruct()` writer + `check_continuity` recovery path with
      degraded verdict/recovery surface; `refresh_validation` receipt keys

## 3. Gate

- [ ] 3.1 full suite + ruff + validate + governance + parity → PR
      fix/issue-529-turn-record-self-heal → dev

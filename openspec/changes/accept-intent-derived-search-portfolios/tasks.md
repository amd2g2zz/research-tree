## 1. Parent acceptance boundary

- [x] 1.1 Add a focused parent acceptance test for verified child receipt
  ancestry, current delivery metadata, and current-only rollback semantics.
- [x] 1.2 Rebind group 74 to its reachable squash-merge verification result and
  update group 27, the issue map, delivery matrix, and umbrella #83 tasks to
  the parent-only acceptance boundary.

## 2. Controlled comparison

- [x] 2.1 Add a failing fixture-validation test that recomputes rediscovery,
  coverage, depth, and decision-closure deltas from normalized observations.
- [x] 2.2 Add the bounded static historical-baseline fixture with explicit
  limitations, trace references, and a forward non-release manifest link.

## 3. Verification and evidence

- [x] 3.1 Run the exact group-27 aggregate command after the source commit and
  record its local-only source-bound receipt.
- [ ] 3.2 Mark group 27 and the #83 parent tasks verified only after strict
  OpenSpec, full regression, package, governance, and delivery-gate checks
  pass at the final PR head.

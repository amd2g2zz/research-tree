# design — single-seat-verification

The engine records receipts in-memory keyed by task and persists a
`provider.action` event per verification (the audit trail). Method
requirements are declarative (the METHOD_REQUIREMENTS table); convergence
audit counts refutation rounds per claim. The dual-seat upgrade (#564) wraps
this engine with the plaintiff seat.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Dual-seat at T1 (T2 scope; the quota is the single-seat forerunner).
- Accepting non-content-addressed evidence (sha256 refs enforced — the trust
  face requires verifiable anchors).
- Promoting single-source claims (docs 01: 单源永不升级).

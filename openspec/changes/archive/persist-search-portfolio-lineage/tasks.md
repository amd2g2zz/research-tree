## 1. Canonical lineage contract

- [x] 1.1 Add focused failing tests for immutable, evidence-bound portfolio
  lineage and the portfolio-specific worker-finish gate.
- [x] 1.2 Implement the coordinator-owned lineage artifact and exact reference
  validation without changing the settled SearchPortfolio execution contract.

## 2. Bounded coordinator decisions

- [x] 2.1 Add failing tests for an inside-authority CorrectionEvent pivot,
  invalid correction zero-write behavior, and requester-controlled human
  reopening.
- [x] 2.2 Invoke `apply_correction()` for an authorized pivot and prove #153
  stale-state quarantine contains the persisted lineage and rejects later
  portfolio worker finish.

## 3. Governance and verification

- [x] 3.1 Register planned group 77, issue map, delivery capability, and
  execution tasks after the source contract is established.
- [x] 3.2 Run the group-77 acceptance and record a local-only source-bound
  receipt after the source commit.
- [x] 3.3 Run focused and full regression, strict OpenSpec/governance, package,
  formatting, and diff checks before handoff.

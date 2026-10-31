# design — dual-seat-adversarial

The DualSeatEngine wraps the #558 single-seat VerificationEngine (the seats
produce VerificationInput-compatible reports that flow through the same
provider.action audit path). Equal budgets enforced structurally
(budgetPerSeat applied to both). Posterior shift combines findings into a
direction + discovery rate.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Dual-seat for all claims (cost doubles — the risk-register mitigation keeps
  non-mob claims single-seat with the #558 quota).
- Pooled EVSI budget (independent settlement is the docs mandate).
- Defense-first ordering (先攻后守 is the adversarial asymmetry).

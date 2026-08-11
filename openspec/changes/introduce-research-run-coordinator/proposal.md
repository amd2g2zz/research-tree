# Introduce ResearchRunCoordinator

## Mission

Make one SQLite-backed `ResearchRunCoordinator` the only writer of canonical
run lifecycle, transition, recovery, supersession, and completion state.

## Scope

- Versioned run-state artifacts and lifecycle-matrix transitions.
- Exact alignment-handoff and Blueprint Target initialization.
- Atomic event/state writes with expected-revision and idempotency checks.
- Completion obligations, why-not-complete diagnostics, leases, and recovery.

## Non-Goals

- Adaptive policy, mutual alignment, or host-specific adapters.
- Replacing existing domain compilers; they remain inputs/translators.

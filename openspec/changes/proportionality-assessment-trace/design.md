# Design: proportionality-assessment-trace

## Approach

Registry append (the designed extension mechanism — `TraceTypeRegistry` is
immutable and append-only), then one derivation branch.

### Trace shape

`proportionality_assessment` requires four structural fields:

- `direction` — `over` (simple goal, disproportionate design) or `under`
  (grand goal, orders-of-magnitude constraint);
- `finding` — the named disproportion;
- `alternative` — the simpler sufficient design (over) or the binding
  magnitude conflict (under);
- `reframing` — the nearest feasible reframing (wired to SKILL Protocol 2's
  infeasibility disposal vocabulary).

Verification stays presence+schema (`verify_traces`), per ADR-008: the
engine never judges whether the assessment is *right* — that is the
composer's craft, and the strategy display fails without the trace.

### Derivation

`_gap_required_traces` keeps its disputed/reopen → `guess-statement` branch
(misunderstood intent is not a proposal evaluation). The two proposal-shaped
branches now return `("option-set", "proportionality_assessment")` and
`("possibility-survey", "proportionality_assessment")`.

### Layer composition (no conflict with existing paths)

1. Alignment-phase hint (this trace — engine-required, prompt-composed).
2. User insists → existing waive path (#491 waive machinery).
3. Survives to compilation → compile-time conflict rejection (#292 item 10).

## impact_scope

- `DEFAULT_TRACE_REGISTRY` / `INITIAL_TRACE_TYPES` (six → seven entries)
- `_gap_required_traces` (alignment_graph.py)
- references/alignment-craft.md, regenerated packages (prose + trace schema)
- tests/test_turn_contract.py + test_contract_emission.py: pins updated to
  the seven-type contract

## rejected_designs

- **Engine enum action "emit concern"**: behavior enumeration violates the
  #501 contract; the trace is verified, the content is composed.
- **Keyword checklist for disproportion** (e.g. matching "CNN" +
  "string matching"): content policing is prompt-layer craft; the engine
  would be both brittle and over-authoritative.
- **Separate necessity validator on Finding Packs**: the check belongs at
  the alignment turn where proposals form, not at ingestion.

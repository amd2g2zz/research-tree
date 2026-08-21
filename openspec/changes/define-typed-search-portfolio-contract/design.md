## Context

The Alpha2 acquisition specification already requires a SearchPortfolio and a
method/tool registry, while the only runtime object named portfolio is the
scheduler's unrelated `work-portfolio`. Parent issue #83 remains responsible
for deriving a portfolio from intent, persisting it, projecting it through
policy, and dispatching it. This child supplies only the strict, dependency
free value objects that those later layers can consume.

## Goals / Non-Goals

**Goals:**

- Define immutable, strictly decoded SearchPortfolio and MethodRegistry value
  objects with explicit JSON schemas and public exports.
- Bind every selected method to one known method/provider registration,
  capability, failure boundary, availability, and any degradation state.
- Preserve selected and rejected method reasons as bounded enum values, while
  retaining only identifier-shaped query references rather than query text or
  private prompts.
- Make logical portfolios serialize in a canonical order and expose a direct
  method/provider independence check for later policy consumers.

**Non-Goals:**

- Deriving subquestions or selections from IntentModel, WorkingBrief, policy,
  evidence deficits, or prior outcomes.
- Persisting a portfolio, emitting SourceCapture or checkpoints, dispatching
  work, adding a CLI, or changing coordinator, policy, or source-capture code.
- Adding batch coverage assessment or closing parent issue #83 / group 27.

## Decisions

1. **Use direct immutable value objects and strict exact-key decoding.**
   `SearchPortfolio`, `MethodRegistry`, and their nested values validate types,
   identifiers, enum values, uniqueness, and unknown fields at construction or
   `from_dict()` boundaries. This follows the repository's content-contract
   pattern and avoids an extra schema-validation dependency.

   The strict public payload uses only `search-portfolio-v2.json`. The
   superseded planning schema and fixture are removed rather than exposed
   through a compatibility reader, alias, or migration path.

2. **Model a method boundary as a method/provider pair.** A registration owns
   one pair, its capability, its failure boundary, and an availability state.
   A selected pair must resolve in the registry and cannot be unavailable.
   Degraded selection remains explicit in the serialized registration state so
   later policy can make a separate trade-off; this child does not choose it.

3. **Represent reasons as controlled vocabularies.** Selected entries carry
   one `selection_reason`; rejected entries carry one `rejection_reason`.
   Query references must be stable identifiers. The contract therefore carries
   auditable intent without becoming a store for raw queries, prompts, secrets,
   or private reasoning.

4. **Expose rather than enforce cross-boundary sufficiency.** A portfolio may
   validly have one selected method, but
   `has_independent_method_provider_boundaries()` reports true only when the
   requested count has distinct method IDs and distinct provider IDs. Later
   planning decides whether a particular decision slot requires that coverage.

5. **Canonicalize unordered collections.** Subquestions, selections,
   rejections, and reassessment dispositions are sorted by stable keys before
   serialization. `to_dict()` is therefore deterministic without a separate
   persistence or hashing layer.

## Risks / Trade-offs

- **[The parent contract eventually needs richer fields]** -> Keep this child
  focused on stable identifiers and enum reasons; add a versioned successor
  rather than accepting arbitrary JSON metadata.
- **[A registry incorrectly reports availability]** -> Preserve the declared
  degraded/unavailable state and fail closed for unavailable selections; policy
  ownership remains with the later parent slice.
- **[A caller attempts to smuggle raw queries into the contract]** -> Accept
  query references only when they match the repository identifier grammar.

## Migration Plan

No migration reader, legacy alias, or deprecated fixture is retained. Later
#83 children may construct and persist the current value objects. Rollback
consists of declining to emit a typed portfolio when validation fails;
historical acquisition state remains untouched.

## Open Questions

None. Batch coverage, persistence, policy projection, and coordinator use are
explicitly deferred to later #83 child issues.

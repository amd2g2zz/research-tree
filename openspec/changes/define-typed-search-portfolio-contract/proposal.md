## Why

The Alpha2 acquisition specification names a SearchPortfolio, but the runtime
has no typed contract that can prove its method/provider boundaries or reject
malformed and unavailable selections. A compact contract is needed before
later child issues derive, persist, or dispatch portfolio plans.

## What Changes

- Add immutable, strictly decoded value objects for a search portfolio,
  subquestions, method registrations, selections, and reassessment policy.
- Add a `MethodRegistry` that resolves registered method/provider pairs and
  refuses unavailable selections.
- Record selected and rejected method reasons without retaining raw query text
  or private prompts; selection query references are stable identifiers only.
- Register planned Alpha2 group 48 and GitHub issue #163 with an exact focused
  contract acceptance command.

## Capabilities

### New Capabilities

- `typed-search-portfolio-contract`: Strict, deterministic SearchPortfolio
  and MethodRegistry value-object contract.

### Modified Capabilities

- None.

## Impact

Adds `src/research_tree/search_portfolio.py`, exports its public contract from
`research_tree`, adds `tests/test_search_portfolio.py`, adds the strict
current SearchPortfolio JSON schema, and registers group 48 in the Alpha2
governance registries and umbrella task list. The superseded planning schema
and fixture are removed rather than retained as a compatibility surface. It
intentionally does not change planning, persistence, policy, source capture,
coordinator, CLI, or parent group 27.

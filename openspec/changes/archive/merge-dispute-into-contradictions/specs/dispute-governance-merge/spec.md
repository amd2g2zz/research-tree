## ADDED Requirements

### Requirement: Dispute governance lives in the contradictions module

The package SHALL expose dispute governance from
`research_tree.contradictions` only. The module `research_tree.dispute` SHALL
NOT exist, and no module, script, or hook SHALL import it.

#### Scenario: Single import source

- **WHEN** production code imports dispute symbols
- **THEN** the import source is `research_tree.contradictions`, and the
  grep gate `grep -rn "from .dispute\|research_tree.dispute" src/ scripts/
  hooks/ --include="*.py"` reports zero matches

#### Scenario: Module retired

- **WHEN** a caller attempts `import research_tree.dispute`
- **THEN** the import raises `ModuleNotFoundError`, locked by a test

### Requirement: The merge changes no production behavior

The coordinator pressure-signal path SHALL keep byte-identical behavior: same
validation errors, same artifact kinds, same payload schema, same audit-trail
reconciliation. KIND constants SHALL keep their wire values. The existing
8-state contradiction classification SHALL be unchanged (additive-only merge).

#### Scenario: Stored payloads stay decodable

- **WHEN** `dispute_packet_from_payload` decodes a stored dispute-ledger
  payload
- **THEN** decoding succeeds without migration; the payload schema is
  unchanged

#### Scenario: Existing classification untouched

- **WHEN** the contradiction detector classifies claims after the merge
- **THEN** the 8-state classification behavior and existing `__all__` exports
  are unchanged; the merge is additive-only

### Requirement: Dead dispute entrypoints retire

The four dead dispute entrypoints SHALL NOT exist in the merged module, its
`__all__`, or any other surface: `derive_dispute_from_contradiction`,
`derive_with_disputes`, `claim_ids_in`, and `record_provider_validation` (all
had zero consumers in production, scripts, hooks, and tests). Negative tests
SHALL lock their absence.

#### Scenario: Negative lockout tests

- **WHEN** the merged-module suite runs
- **THEN** a test asserts `research_tree.dispute` cannot be imported and the
  four retired entrypoint names are absent from
  `research_tree.contradictions` and its `__all__`

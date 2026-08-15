## 1. Contract and governance

- [x] 1.1 Inventory the coordinator operations after #149, #151, #164, and
  #165, and exclude APIs without a direct current-only command contract.
- [x] 1.2 Register issue #150 / group 84 with its prerequisite groups and
  focused acceptance command.

## 2. Red CLI coverage

- [x] 2.1 Add a direct coordinator/CLI parity fixture for HostEvent ingestion,
  recovery, completion diagnostics, and a blocked completion.
- [x] 2.2 Cover the required workspace, JSON result envelope, stable error
  classifications, and absence of unsupported or retired commands.

## 3. Current-only implementation

- [x] 3.1 Replace the empty reserved parser with the `run` grammar and exactly
  four coordinator-backed verbs.
- [x] 3.2 Emit canonical JSON results without aliases, fallback imports,
  migration behavior, or writes outside the provided workspace.

## 4. Documentation and verification

- [x] 4.1 Document only the current commands and validate generated package
  parity plus an installed-wheel smoke invocation.
- [ ] 4.2 Run focused tests, Ruff, strict OpenSpec, governance, documentation,
  package, and GitNexus change checks; then record the group-84 receipt.

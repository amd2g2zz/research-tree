## 1. Stable contract

- [x] 1.1 Replace the advertised raw coordinator surface with six stable lifecycle verbs.
- [x] 1.2 Persist lifecycle requests through the canonical ledger and project workspace.
- [x] 1.3 Return versioned authority revision and fail-closed readiness data.

## 2. Safety and compatibility

- [x] 2.1 Keep raw HostEvent and SQLite operations behind an acknowledged internal parser.
- [x] 2.2 Make verification pending until independent canonical evidence exists.
- [x] 2.3 Cover lifecycle creation, resume, status, verification, and internal transport regression paths.

## 3. Distribution and evidence

- [x] 3.1 Document the common lifecycle in README and all host package templates.
- [x] 3.2 Rebuild generated host packages and verify source/package parity.
- [x] 3.3 Run focused tests, wheel smoke, formatting, OpenSpec, governance, and delivery checks.

## 1. Isolated Closure Contract

- [x] 1.1 Add failing staging tests for every documented Hermes executable
  entrypoint in an unrelated working directory with empty `PYTHONPATH`.
- [x] 1.2 Add failing tests that a missing transitive module fails validation
  closed with its exact dependency path.
- [x] 1.3 Add a bounded isolated provider-failure/recovery regression fixture.

## 2. Package And Staging Implementation

- [x] 2.1 Declare and validate the deterministic Hermes executable closure in
  the package builder.
- [x] 2.2 Reuse the closure for Hermes staging and compatibility validation.
- [x] 2.3 Rebuild generated Hermes package output from authoring sources.

## 3. Verification And Delivery

- [x] 3.1 Run focused tests, Ruff, package parity, strict OpenSpec, and review
  the generated diff.
- [x] 3.2 Run the full issue acceptance suite and source-bound delivery checks.

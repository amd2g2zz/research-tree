## ADDED Requirements

### Requirement: Tool and oracle execution is sandboxed and allowlisted

Code execution, document/image parsing, repository commands, network retrieval, and oracle commands SHALL run under a declared safety tier with allowlisted paths, executables, network endpoints, environment variables, resource limits, and output destinations.

#### Scenario: Oracle requests an undeclared command

- **WHEN** an OracleSpec invokes a binary or network target outside its permission profile
- **THEN** execution is denied and an auditable policy-violation result is emitted

### Requirement: Workspace and artifact paths are enforced

All reads and writes performed by workers, adapters, hooks, CAS, and migration tools MUST resolve within registered boundaries; symlink/junction escapes and path traversal SHALL be rejected.

#### Scenario: A symlink escapes the workspace

- **WHEN** an action resolves a path outside its declared root
- **THEN** the action fails before I/O and the run remains non-complete

### Requirement: Secrets and private reasoning do not enter evidence

Trace, Finding Pack, report, evaluation, and release-manifest serializers SHALL redact credentials, tokens, private prompts, hidden-oracle content, raw provider diagnostics, and private chain-of-thought while retaining safe error metadata and reproducibility fields.

#### Scenario: Provider error contains sensitive details

- **WHEN** a gateway returns a raw error payload
- **THEN** only an opaque code, provider/model identity, retry category, attempt id, and safe log reference are persisted

### Requirement: Analysis Checkpoints exclude private reasoning and secrets

The AnalysisCheckpoint schema SHALL permit only structured facts, evidence refs, hypothesis states, contradictions, uncertainties, method outcomes, and next-action proposals. It SHALL reject full prompts, hidden-oracle content, credentials, raw provider diagnostics, and private chain-of-thought.

#### Scenario: Worker submits a narrative reasoning transcript

- **WHEN** a checkpoint contains unrestricted internal reasoning or a secret-bearing prompt fragment
- **THEN** ingestion redacts or rejects the prohibited field while preserving safe evidence references and resumable task state

### Requirement: Network and licensing policy is recorded

External acquisition SHALL record network permission, source license/access note, retrieval time, and whether the source may be redistributed. Unlicensed or inaccessible material SHALL not be presented as a reproducible public fixture.

#### Scenario: Source cannot be redistributed

- **WHEN** a claim depends on a restricted source
- **THEN** the evidence records the restriction and the release report labels the claim as non-reproducible or substitutes an allowed source

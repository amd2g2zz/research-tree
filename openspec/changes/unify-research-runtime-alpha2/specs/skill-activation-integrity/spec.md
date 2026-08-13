## ADDED Requirements

### Requirement: Host activation is distinct from package discovery
The runtime MUST distinguish package discovery metadata, current package
installation, and full skill-body activation. A package validator or a file
read MUST NOT be reported as proof that the active model turn received the
skill body.

#### Scenario: A direct file link is supplied
- **WHEN** a requester supplies a `SKILL.md` path or Markdown link without the
  host's native skill invocation
- **THEN** the runtime MUST classify the turn as `activation_unverified`, give
  the host-specific invocation command, and MUST NOT claim that research-tree
  is active

#### Scenario: The installed target is not the selected current package
- **WHEN** the target already exists but does not resolve to the selected
  current package
- **THEN** setup status MUST report `unsupported` and MUST NOT treat the target
  as a migration input, unlink, move, replace, or otherwise mutate it

### Requirement: Each host has an explicit activation proof
Each generated host package MUST contain a host-specific activation marker and
probe contract. The probe MUST be side-effect free and return one exact
sentinel response. Codex clients using app-server MUST include a typed `skill`
input item with the package path; Claude Code and Hermes MUST use their native
slash invocation. A bare text marker or file read is not sufficient proof.

#### Scenario: The host probe is invoked natively
- **WHEN** the host receives its native activation probe in a fresh session
- **THEN** the model MUST return the package's exact host sentinel and MUST NOT
  start research or call a research tool

#### Scenario: The package is stale or malformed
- **WHEN** the marker, required activation resources, encoding, or host package
  identity does not match
- **THEN** the probe and package validator MUST fail with a stable diagnostic;
  they MUST NOT emit a successful activation receipt

### Requirement: Activation receipts expose evidence boundaries
An activation receipt MUST record host, package path, package digest, sentinel,
schema version, and workspace correlation. It MUST explicitly state that it
does not prove model compliance after injection. Research execution MAY begin
only after a successful package check and a host-visible activation proof, or
after recording the host limitation as an unresolved diagnostic.

#### Scenario: Static checks pass but the host cannot prove body injection
- **WHEN** setup can verify the package and target but the host has no live
  activation event or probe result
- **THEN** setup status MUST report `static_ready` with
  `live_activation: unproven`, never `active`

### Requirement: Cross-host activation parity is release evidence
The release test suite MUST run the native activation probe for Codex, Claude
Code, and Hermes packages independently, verify that package paths and
sentinels do not cross-contaminate, and retain the exact command output. A
missing host CLI is an unavailable probe, not a passing result.

#### Scenario: One host is unavailable
- **WHEN** a supported host CLI is not installed in the test environment
- **THEN** the result MUST be marked `unavailable` with the missing capability
  and the release gate MUST not silently count it as parity evidence
